#!/usr/bin/env python3
"""Patch TQ-specific additions into base vLLM files without replacing them.

This script runs inside the Docker container at build time to surgically
add TurboQuant support to files that have version-sensitive code.
Files that are entirely new (turboquant module, triton kernels) are
copied directly via COPY in the Dockerfile.
"""
import re
import sys

VLLM = "/usr/local/lib/python3.12/dist-packages/vllm"


def patch_torch_utils():
    """Add TQ dtype mappings and helper functions to torch_utils.py."""
    path = f"{VLLM}/utils/torch_utils.py"
    with open(path) as f:
        content = f.read()

    patched = False

    # 1. Add TQ dtypes after the fp8_e5m2 entry
    if "tq-k8v4" not in content:
        content = content.replace(
            '"fp8_e5m2": torch.uint8,',
            '"fp8_e5m2": torch.uint8,\n'
            '    "tq-k8v4": torch.uint8,\n'
            '    "tq-t4nc": torch.uint8,\n'
            '    "tq-k3v4nc": torch.uint8,\n'
            '    "tq-t3nc": torch.uint8,',
        )
        patched = True
        print("torch_utils.py: patched TQ dtypes")

    # 2. Add is_quantized_kv_cache (Alberto's branch moved it here from
    #    v1/attention/backend.py — overlaid files import from here)
    if "def is_quantized_kv_cache" not in content:
        funcs = (
            '\n\ndef is_quantized_kv_cache(kv_cache_dtype: str) -> bool:\n'
            '    return kv_cache_dtype.startswith("fp8") or '
            'kv_cache_dtype.endswith("per_token_head")\n'
            '\n\ndef kv_cache_uses_per_token_head_scales('
            'kv_cache_dtype: str) -> bool:\n'
            '    """Return True if *kv_cache_dtype* needs '
            'per-token-head scales."""\n'
            '    return kv_cache_dtype.endswith("per_token_head")\n'
        )
        # Append before the last line or at end of file
        content = content.rstrip() + funcs
        patched = True
        print("torch_utils.py: patched is_quantized_kv_cache + "
              "kv_cache_uses_per_token_head_scales")

    if not patched:
        print("torch_utils.py: already patched")

    with open(path, "w") as f:
        f.write(content)


def patch_cuda_platform():
    """Add TQ backend routing to get_attn_backend_cls."""
    path = f"{VLLM}/platforms/cuda.py"
    with open(path) as f:
        content = f.read()

    if "TURBOQUANT" in content:
        print("cuda.py: already patched")
        return

    # No new import needed — base already imports AttentionBackendEnum
    # from vllm.v1.attention.backends.registry (and registry.py is overlaid
    # with the TURBOQUANT enum value)

    # Add TQ routing before the normal backend priority lookup.
    # Find the line that calls _get_backend_priorities in get_attn_backend_cls
    # and insert the TQ check before it.
    tq_check = (
        "\n        # TurboQuant KV cache: route directly to TQ backend\n"
        "        kv_cache_dtype = attn_selector_config.kv_cache_dtype\n"
        "        if kv_cache_dtype is not None and kv_cache_dtype.startswith('tq-'):\n"
        "            return [(AttentionBackendEnum.TURBOQUANT, 0)], {}\n"
    )

    # Insert before "backend_priorities = _get_backend_priorities("
    marker = "        backend_priorities = _get_backend_priorities("
    if marker in content:
        content = content.replace(marker, tq_check + "\n" + marker)
        with open(path, "w") as f:
            f.write(content)
        print("cuda.py: patched TQ backend routing")
    else:
        # Try alternate: look for the call inside get_attn_backend_cls
        marker2 = "backend_priorities, extra_kw = _get_backend_priorities("
        if marker2 in content:
            content = content.replace(marker2, tq_check + "\n        " + marker2)
            with open(path, "w") as f:
                f.write(content)
            print("cuda.py: patched TQ backend routing (alt marker)")
        else:
            print("cuda.py: WARNING - could not find insertion point!", file=sys.stderr)
            sys.exit(1)


def patch_arg_utils():
    """Add TQ boundary layer protection after CacheConfig construction."""
    path = f"{VLLM}/engine/arg_utils.py"
    with open(path) as f:
        content = f.read()

    if "TQ_BOUNDARY_LAYERS" in content:
        print("arg_utils.py: already patched")
        return

    # Insert TQ boundary protection block after CacheConfig(...) constructor,
    # right before "ray_runtime_env = None"
    tq_block = (
        "\n"
        "        # TurboQuant boundary layer protection: auto-populate skip layers.\n"
        "        import os as _os\n"
        "        _n_boundary = int(_os.environ.get('TQ_BOUNDARY_LAYERS', '2'))\n"
        "        _hf_tc = model_config.hf_text_config\n"
        "        _has_hetero_heads = (\n"
        "            getattr(_hf_tc, 'head_dim', None) is not None\n"
        "            and getattr(_hf_tc, 'global_head_dim', None) is not None\n"
        "            and _hf_tc.head_dim != _hf_tc.global_head_dim\n"
        "        )\n"
        "        if (\n"
        "            resolved_cache_dtype.startswith('tq-')\n"
        "            and _n_boundary > 0\n"
        "            and not model_config.is_hybrid\n"
        "            and not _has_hetero_heads\n"
        "        ):\n"
        "            from vllm.model_executor.layers.quantization.turboquant.config import (\n"
        "                TurboQuantConfig,\n"
        "            )\n"
        "            _num_layers = model_config.hf_text_config.num_hidden_layers\n"
        "            _boundary = TurboQuantConfig.get_boundary_skip_layers(\n"
        "                _num_layers, _n_boundary\n"
        "            )\n"
        "            _existing = set(cache_config.kv_cache_dtype_skip_layers)\n"
        "            _all = _existing | set(_boundary)\n"
        "            _numeric = sorted([x for x in _all if x.isdigit()], key=int)\n"
        "            _non_numeric = sorted(x for x in _all if not x.isdigit())\n"
        "            cache_config.kv_cache_dtype_skip_layers = _numeric + _non_numeric\n"
        "\n"
    )

    marker = "        ray_runtime_env = None"
    if marker in content:
        content = content.replace(marker, tq_block + marker)
        with open(path, "w") as f:
            f.write(content)
        print("arg_utils.py: patched TQ boundary layer protection")
    else:
        print("arg_utils.py: WARNING - could not find insertion point!",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    patch_torch_utils()
    patch_cuda_platform()
    patch_arg_utils()
    print("All patches applied.")
