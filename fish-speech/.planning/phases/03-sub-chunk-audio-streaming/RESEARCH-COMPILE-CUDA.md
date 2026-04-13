# torch.compile + CUDA Graph Constraints for Sub-Chunk Streaming

## What's Currently Compiled

### Compiled: `decode_one_token_ar` (the only compiled function)

```
# inference.py, init_model(), line 422
decode_one_token = torch.compile(
    decode_one_token,
    backend="inductor",
    mode="reduce-overhead",
    fullgraph=False,
)
```

- **Target function:** `decode_one_token_ar` (line 115-200)
- **Backend:** `inductor` (on CUDA), `aot_eager` (fallback)
- **Mode:** `reduce-overhead` -- enables CUDA graph capture under the hood
- **fullgraph:** `False` -- graph breaks are tolerated; Dynamo splits into subgraphs

This function does one complete decode step:
1. `model.forward_generate(x, input_pos, ...)` -- slow (main) transformer forward pass
2. Sampling from logits (temperature, top_p, top_k)
3. RAS (Repetition Aware Sampling) -- tensor-only conditional via `torch.where`
4. Fast transformer loop: `model.forward_generate_fast(hidden_states, input_pos)` x num_codebooks
5. Returns stacked codebooks `(num_codebooks+1, 1)`

### NOT Compiled

| Component | File | Why |
|-----------|------|-----|
| `decode_n_tokens` | inference.py:203 | Outer loop calling compiled `decode_one_token_ar`; contains Python control flow, tqdm, break |
| `generate` | inference.py:262 | Orchestrator: builds tensors, calls prefill + `decode_n_tokens` |
| `generate_long` | inference.py:798 | Generator function (`yield`); text chunking, conversation management |
| DAC `from_indices` | modded_dac.py:925 | Never compiled. Called separately after full token generation |
| DAC `decoder` | modded_dac.py:848 | Convolutional decoder, never compiled |
| DAC `quantizer.decode` | via `from_indices` | Codebook lookup, never compiled |

### Inductor Config (Global)

```python
torch._inductor.config.coordinate_descent_tuning = True
torch._inductor.config.triton.unique_kernel_names = True
torch._inductor.config.fx_graph_cache = True  # if available

# When compile=True:
torch._inductor.config.force_fuse_int_mm_with_mul = True
torch._inductor.config.coordinate_descent_check_all_directions = True
```

### KV Cache: Static

The model uses a static KV cache pre-allocated at `max_seq_len` (line 302-308). This is critical -- it means the compiled `decode_one_token_ar` sees fixed tensor addresses for cache reads/writes across all decode steps, making CUDA graph replay safe.

```python
model.setup_caches(max_batch_size=1, max_seq_len=model.config.max_seq_len, dtype=...)
```

---

## Constraint Analysis

### Constraint 1: Can `yield` exist inside a torch.compiled function?

**No.** TorchDynamo traces Python bytecode into FX graphs. Generator `yield` introduces stateful, lazy control flow that cannot be captured in a static graph. A `yield` inside a compiled function would cause a graph break at minimum, or an error with `fullgraph=True`.

**Impact on us: NONE.** Our `yield` statements are in `generate_long` (line 1008, 1018) and `TTSInferenceEngine.inference` (line 80, 120, 134, 146, 154). Neither of these functions is compiled. The compiled boundary is `decode_one_token_ar` -- a pure function with no yields.

### Constraint 2: Can we yield BETWEEN calls to a compiled function?

**Yes, safely.** This is the standard LLM inference pattern (GPT-Fast, vLLM, SGLang):

1. Call compiled `decode_one_token` -- CUDA graph replays
2. Control returns to Python (CPU side)
3. Do whatever CPU work you want (yield token, update state, stream audio)
4. Call compiled `decode_one_token` again -- same CUDA graph replays

The CUDA graph is a recorded sequence of GPU operations for a single invocation of the compiled function. Between replays, the CPU is free to do anything. The ~2ms GPU idle "bubble" between graph replays (observed in SGLang) is actually the natural window for CPU-side streaming work.

**Key requirement:** Input tensor shapes and memory addresses must remain identical between calls. Our code already satisfies this:
- `cur_token`: always `(1, num_codebooks+1, 1)` -- single token decode
- `input_pos`: always `(1,)` -- scalar position, only value changes
- `temperature`, `top_p`, `top_k`: fixed tensors, never change
- `semantic_logit_bias`: fixed `(1, 1, vocab_size)` tensor
- KV cache: static, pre-allocated at max length

### Constraint 3: Variable iteration counts in the decode loop

**Not a problem.** CUDA graphs are captured per-invocation of `decode_one_token_ar`, not for the entire `decode_n_tokens` loop. Each loop iteration replays the same captured graph. The number of iterations can vary freely -- early termination on `im_end_id` is handled in Python outside the compiled function.

### Constraint 4: DAC decoder with variable sequence lengths

`DAC.from_indices()` is NOT compiled. It runs in eager mode. This means:

- **No CUDA graph constraints apply to DAC decode calls**
- We can call `from_indices()` with any sequence length at any time
- No recompilation penalty
- Each call is an independent eager forward pass through the convolutional decoder

The DAC decoder (`decoder_rates=[8, 8, 4, 2]`, `decoder_dim=1536`, `causal=True`) is a stack of causal transposed convolutions. Since `causal=True`, it has no lookahead -- only leftward receptive field. This makes chunked decoding architecturally sound, though boundary artifacts from the convolutional receptive field still need overlap handling (already addressed by `StreamingCrossfader` in the codebase).

### Constraint 5: Prefill vs decode shape difference

The prefill call (line 343-353) passes the full prompt `(1, codebook_dim, T)` where T varies. The decode calls pass `(1, codebook_dim, 1)`. With `fullgraph=False`, this triggers:

1. First call (prefill): Dynamo traces + Inductor compiles + CUDA graph records for shape T
2. First decode call: Different shape (1) triggers re-trace + recompile + new CUDA graph recording
3. Subsequent decode calls: Replay the decode CUDA graph (same shape every time)

This is already the current behavior -- no change needed. The prefill uses the uncompiled `decode_one_token_ar` directly anyway (line 341: `prefill_decode = decode_one_token_ar` -- the raw function, not the compiled version), so actually only the decode shape is ever seen by the compiled function.

**Wait -- correction.** Looking more carefully at the code:

```python
prefill_decode = decode_one_token_ar  # line 341 -- raw function
first_token = prefill_decode(...)      # line 343 -- NOT compiled

# Then:
x = decode_n_tokens(
    ...
    decode_one_token=decode_one_token,  # line 370 -- this IS the compiled version
)
```

So the prefill is NEVER compiled. Only the single-token decode steps go through the compiled path. This is clean -- the compiled function always sees shape `(1, codebook_dim, 1)` for `x` and `(1,)` for `input_pos`.

---

## Known Workarounds

### Workaround 1: Yield in outer loop (ALREADY the correct pattern)

The decode loop in `decode_n_tokens` calls the compiled function, then does Python work. To add streaming, we add yield points in this loop (or a modified version of it). The compiled function is unaware of the yield -- it's pure GPU work.

```python
# Conceptual streaming pattern (no compiled code changes needed):
for i in range(num_new_tokens):
    next_token = compiled_decode_one_token(...)  # CUDA graph replay
    tokens.append(next_token)
    
    if len(tokens) >= sub_chunk_size:
        yield tokens  # CPU-side work, between CUDA graph replays
        tokens = []
```

### Workaround 2: `torch.compiler.disable` for specific functions

If we ever needed to call a function that breaks compilation inside a compiled region:

```python
@torch.compiler.disable
def my_non_compilable_function(...):
    ...
```

**Not needed for our case** -- the compiled boundary (`decode_one_token_ar`) doesn't need modification.

### Workaround 3: Selective/piecewise compilation (vLLM pattern)

vLLM wraps attention in a custom op (`torch.ops.vllm.unified_attention_with_output`) so Dynamo doesn't trace it, then compiles the rest. This lets them handle dynamic KV cache shapes inside compiled code.

**Not needed for our case** -- our KV cache is already static.

### Workaround 4: Padding to bucketed shapes for CUDA graph reuse

If input shapes vary, pad to a small set of fixed sizes to limit CUDA graph re-recordings. Each unique shape records a separate CUDA graph (64KB device memory per kernel launch).

**Not needed for our case** -- decode always uses shape `(1, codebook_dim, 1)`.

---

## Performance Implications

### Adding yield points in `decode_n_tokens`: ~0 overhead

The yield happens between CUDA graph replays. The GPU idle bubble (~2ms per step, per SGLang measurements) already exists between replays for CPU bookkeeping. Adding a yield + DAC decode in this window uses CPU time that was otherwise idle (while waiting for the next GPU dispatch).

However, we must be careful about:

1. **Synchronization cost**: If we call `torch.cuda.synchronize()` or move tensors to CPU between decode steps to check token values or accumulate tokens, we force a GPU sync. The current code already does `cur_token[0, 0, -1] == im_end_id` which is a scalar comparison -- this likely triggers a sync. This is existing behavior, not new overhead.

2. **DAC decode latency in the streaming path**: When we yield sub-chunk audio, we call `DAC.from_indices()` on accumulated tokens. This is an eager GPU operation that runs on the same CUDA stream. The GPU must finish the DAC decode before the next `decode_one_token` CUDA graph replay can start. For small sub-chunks (~50 tokens = ~0.58s audio), DAC decode takes roughly 5-15ms on RTX 5090. This is within the GPU bubble window and should not significantly impact token generation throughput.

3. **Memory**: No additional VRAM from the compile/CUDA graph side. The DAC decoder is already loaded in memory. Sub-chunk token accumulation is negligible (a few KB).

### NOT compiling DAC: acceptable

The DAC decoder is a relatively lightweight convolutional network compared to the 36-layer transformer. It processes variable-length inputs and is called infrequently (once per sub-chunk, not once per token). Compiling it would provide marginal speedup at the cost of:
- Recompilation on every new sequence length (or padding overhead)
- Additional CUDA graph recordings eating VRAM
- Complexity for minimal gain

The DAC decode is not on the critical path for TTFA -- the transformer token generation is.

### Current compilation overhead

First invocation triggers compilation (~10-30s depending on model). Subsequent requests reuse compiled graphs. The `fx_graph_cache = True` setting persists compiled graphs across process restarts (if supported by PyTorch version).

---

## Recommendations

### 1. Modify `decode_n_tokens` to yield sub-chunk tokens (SAFE)

Convert `decode_n_tokens` to a generator or add a callback mechanism. This function is NOT compiled -- it's the outer Python loop that calls the compiled `decode_one_token_ar`. Adding yield points here has zero impact on CUDA graph behavior.

**Preferred approach:** Make `decode_n_tokens` yield accumulated tokens every N steps:

```python
def decode_n_tokens(..., sub_chunk_size: int = 50):
    new_tokens = []
    for i in range(num_new_tokens):
        next_token = decode_one_token(...)  # compiled, CUDA graph replay
        new_tokens.append(next_token)
        
        if len(new_tokens) >= sub_chunk_size:
            yield torch.cat(new_tokens, dim=1)
            new_tokens = []
        
        if cur_token[0, 0, -1] == im_end_id:
            break
    
    if new_tokens:
        yield torch.cat(new_tokens, dim=1)
```

### 2. Do NOT touch `decode_one_token_ar` (the compiled function)

No modifications needed to the compiled function. It's a pure single-step decode that produces one token per call. The CUDA graph captures and replays this unchanged.

### 3. Do NOT compile the DAC decoder

Keep `DAC.from_indices()` in eager mode. It handles variable-length inputs naturally, adds negligible latency per sub-chunk, and compiling it would add complexity for minimal benefit.

### 4. DAC decode runs on the same CUDA stream -- no extra sync needed

Since both the transformer (compiled) and DAC (eager) run on the default CUDA stream, operations are naturally serialized. No explicit `torch.cuda.synchronize()` is needed between them. The DAC decode will execute after the last compiled decode step completes.

### 5. Thread architecture unchanged

The current `launch_thread_safe_queue` / worker thread pattern works fine. The worker thread calls `generate_long` which yields `GenerateResponse` chunks. We just need the chunks to come more frequently (sub-chunk level instead of text-batch level).

### 6. The `generate` -> `generate_long` chain needs restructuring

Currently:
- `generate_long` yields once per text batch (after full token generation + all decode steps)
- `generate` calls `decode_n_tokens` which returns all tokens at once
- Sub-chunk streaming requires `decode_n_tokens` to yield partial results

The modification chain:
1. `decode_n_tokens` becomes a generator (yields sub-chunk token batches)
2. `generate` must propagate these yields (becomes a generator or uses callback)
3. `generate_long` yields `GenerateResponse(action="sample")` per sub-chunk instead of per text batch

This is all Python control flow restructuring -- no compilation changes needed.

---

## Summary Table

| Concern | Status | Risk |
|---------|--------|------|
| yield inside compiled function | Not needed -- yield is in outer Python code | NONE |
| yield between compiled calls | Safe -- standard LLM streaming pattern | NONE |
| Variable decode loop iterations | Safe -- CUDA graph is per-call, not per-loop | NONE |
| DAC decode with variable lengths | Safe -- DAC is not compiled, runs eager | NONE |
| CUDA graph shape mismatch | Safe -- decode always uses (1, codebook_dim, 1) | NONE |
| KV cache dynamism | Safe -- already static, pre-allocated at max_seq_len | NONE |
| DAC decode latency on critical path | ~5-15ms per sub-chunk, within GPU bubble | LOW |
| VRAM increase | None from compile/graph side | NONE |
| Compile-time increase | None -- same function compiled | NONE |

**Bottom line:** Sub-chunk streaming is fully compatible with the existing torch.compile + CUDA graph setup. The compiled function (`decode_one_token_ar`) is called identically whether we yield every 50 tokens or every 500 tokens. All streaming logic lives in uncompiled Python code surrounding the compiled calls.

---

## Sources

- [torch.compile documentation (PyTorch 2.11)](https://docs.pytorch.org/docs/stable/generated/torch.compile.html)
- [CUDAGraph Trees documentation](https://docs.pytorch.org/docs/stable/torch.compiler_cudagraph_trees.html)
- [How CUDA Graph Works in torch.compile (GPU Notes)](https://fkong.tech/posts/2025-12-23-cuda-graph-in-torch-compile/)
- [PyGraph: Robust Compiler Support for CUDA Graphs](https://arxiv.org/html/2503.19779v1)
- [torch.compile + vLLM (vLLM Blog)](https://blog.vllm.ai/2025/08/20/torch-compile.html)
- [CUDA Graphs in LLM Inference: Deep Dive](https://dev.to/sfahad/cuda-graphs-in-llm-inference-deep-dive-36pb)
- [Accelerating Generative AI with PyTorch II: GPT, Fast](https://pytorch.org/blog/accelerating-generative-ai-2/)
- [Speed, Python: Pick Two -- CUDA Graphs (Fireworks AI)](https://fireworks.ai/blog/speed-python-pick-two-how-cuda-graphs-enable-fast-python-code-for-deep-learning)
- [torch.compiler.disable documentation](https://docs.pytorch.org/docs/stable/generated/torch.compiler.disable.html)
- [Optimizing Token Generation in PyTorch Decoder Models](https://towardsdatascience.com/optimizing-token-generation-in-pytorch-decoder-models/)
- [SGLang CUDA Graph GPU bubble discussion](https://github.com/sgl-project/sglang/issues/5593)
- [vLLM CUDA Graphs design](https://docs.vllm.ai/en/stable/design/cuda_graphs/)
- [DAC (HuggingFace)](https://huggingface.co/docs/transformers/model_doc/dac)
- [DAC-JAX chunked decode benchmarks](https://arxiv.org/html/2405.11554v1)
- [EnCodec streaming architecture](https://github.com/facebookresearch/encodec)
