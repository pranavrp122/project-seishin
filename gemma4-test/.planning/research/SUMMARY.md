# Research Summary: Gemma 4 26B-A4B NVFP4 + TurboQuant KV

**Synthesized:** 2026-04-14
**Sources:** 5 research documents (RESEARCH.md, RESEARCH-VLLM-SETUP.md, RESEARCH-TQ-PLUGIN.md, RESEARCH-LLAMACPP.md, RESEARCH-NVFP4-TQ-COMPAT.md)

---

## Key Findings

### Stack Decision: vLLM from PR #38479
- **vLLM** is the only viable path for NVFP4 on RTX 5090 (llama.cpp NVFP4 CUDA kernels broken, Issue #21777)
- Must build from **vibhavagarwal5/vllm** fork (TurboQuant native backend, PR #38479)
- Apply **Alberto-Codes' Gemma 4 fixes** (PRs #4 and #6) for hybrid attention support
- Docker image: CUDA 13.0 (cu130) for SM120/Blackwell
- Critical: mount `gemma4_patched.py` to fix NVFP4 MoE scale key mapping

### VRAM Budget Analysis
| Component | Size |
|-----------|------|
| NVFP4 weights | ~15.7 GB |
| FP8 KV cache (32K context) | ~0.4 GB (only 5 global layers scale) |
| TQ KV cache (32K context) | ~0.15 GB (2.66x compression over FP8) |
| vLLM overhead | ~1.5 GB |
| **Total (FP8 KV)** | **~17.6 GB** |
| **Total (TQ KV)** | **~17.35 GB** |

Both fit under 18GB target. TQ saves ~250MB at 32K context — modest gain because Gemma 4's sliding window architecture means only 5 layers need full-context KV.

### Architecture Insight: KV Cache Is NOT the Bottleneck
- 25 of 30 layers use sliding window (1024 tokens) — KV is capped regardless of context length
- Only 5 global layers store full context KV (head_dim=512, 4 KV heads)
- This means TurboQuant's compression benefit is **much smaller** than on dense attention models
- The real VRAM consumer is the 15.7GB model weights

### NVFP4 + TurboQuant Compatibility
- **Confirmed independent code paths** — weight quant and KV quant dispatch separately
- `DISPATCH_BY_KV_CACHE_DTYPE` routes KV ops independently of `--quantization` flag
- Page size issue is about hybrid Mamba+attention models, NOT weight quantization
- `TQFullAttentionSpec` with `next_power_of_2` padding fixes page alignment for Gemma 4
- **Untested combination** — likely works but nobody has publicly validated it

### Risk Register
| Risk | Severity | Mitigation |
|------|----------|------------|
| head_dim=512 untested with TQ | HIGH | Fall back to FP8 KV for global layers |
| SM120 kernel edge cases | MEDIUM | Use cu130 image, test thoroughly |
| gemma4_patched.py version drift | LOW | Pin model version, verify patch on startup |
| Docker image may not exist as tagged | MEDIUM | Have fallback image tags ready |
| ModelOptNvFp4Config default KV method | LOW | CLI `--kv-cache-dtype` should override |

### Rejected Alternatives
- **llama.cpp + NVFP4**: CUDA kernels not implemented (Issue #21777)
- **llama.cpp + MXFP4-MOE**: Works (197 tok/s) but no FP4 tensor core acceleration for all layers
- **TurboQuant pip plugin**: Page size conflict with NVFP4's CUSTOM backend
- **varjoranta fork**: Uses own TQ3 weight compression, doesn't support NVFP4 coexistence

## Staged Testing Approach
1. **Stage 1**: NVFP4 + FP8 KV baseline (known working, validates setup)
2. **Stage 2**: NVFP4 + TurboQuant KV (experimental, the actual goal)
3. **Stage 3**: Benchmark both, compare VRAM/throughput/quality

---
*Synthesized from 5 research documents, 2026-04-14*
