# Research: Restructuring `generate_long` for Partial VQ Token Yielding

## Current Architecture

### Code Flow Diagram

```
generate_long()                    [inference.py:798]
  |
  |-- for each text batch (chunk):
  |     |
  |     |-- Build conversation prompt -> encode_for_inference()
  |     |     -> encoded: (num_codebooks+1, seq_len)  i.e. (11, T_prompt)
  |     |
  |     |-- generate()              [inference.py:262]
  |     |     |
  |     |     |-- Prefill: decode_one_token_ar(prompt)
  |     |     |     -> first_token: (num_codebooks+1, 1)  i.e. (11, 1)
  |     |     |
  |     |     |-- decode_n_tokens()  [inference.py:203]
  |     |     |     |
  |     |     |     |-- for i in range(max_new_tokens):
  |     |     |     |     |-- decode_one_token_ar()  [inference.py:115]
  |     |     |     |     |     |-- model.forward_generate(x, input_pos)
  |     |     |     |     |     |     -> slow AR logits + hidden_states
  |     |     |     |     |     |-- sample main_token (semantic token)
  |     |     |     |     |     |-- model.forward_generate_fast(hidden_states)
  |     |     |     |     |     |     -> fast AR: iterates num_codebooks steps
  |     |     |     |     |     |     -> produces codebook_0..codebook_9
  |     |     |     |     |     |-- return stacked: (num_codebooks+1, 1)
  |     |     |     |     |
  |     |     |     |     |-- Append to new_tokens list
  |     |     |     |     |-- Check for im_end_id -> break
  |     |     |     |
  |     |     |     |-- return torch.cat(new_tokens, dim=1)
  |     |     |     |     -> shape: (num_codebooks+1, T_generated)
  |     |     |
  |     |     |-- Return seq[:, :T+1+T_generated]
  |     |           shape: (num_codebooks+1, T_prompt + T_generated)
  |     |
  |     |-- Extract codes = y[1:, prompt_length:-1]
  |     |     -> shape: (num_codebooks, T_generated) = (10, T_generated)
  |     |
  |     |-- yield GenerateResponse(action="sample", codes=codes)
  |
  |-- yield GenerateResponse(action="next")
```

### Consumer Side (inference engine)

```
TTSInferenceEngine.inference()      [__init__.py:45]
  |
  |-- while True:
  |     |-- response_queue.get() -> WrappedGenerateResponse
  |     |-- result.action != "next":
  |     |     |-- get_audio_segment(result)
  |     |     |     |-- decode_vq_tokens(result.codes)
  |     |     |     |     |-- DAC.from_indices(codes[None])
  |     |     |     |     |     -> codes[None]: (1, 10, T) -> audio: (1, 1, T_audio)
  |     |     |     |     |     where T_audio = T * 2048 (total upsample factor)
  |     |     |     |-- post_fx (pedalboard EQ)
  |     |     |
  |     |     |-- crossfader.process(segment) -> emit blended audio
  |     |     |-- segments.append(segment)
  |     |
  |     |-- result.action == "next": break
  |
  |-- crossfader.flush()
  |-- np.concatenate(segments) -> final audio
```

### Key Shape Facts (S2-Pro)

| Value | Meaning |
|-------|---------|
| `num_codebooks = 10` | LLM config: 1 semantic codebook in slow AR + 9 residual codebooks in fast AR (but counted as 10 fast-AR steps since the semantic token's codebook index is also predicted) |
| `codebook_size = 4096` | Vocabulary size per codebook |
| `codes shape = (10, T)` | Yielded to consumer; rows = codebook levels, cols = timesteps |
| DAC sample_rate = 44100 Hz | Audio output sample rate |
| DAC encoder_rates = [2,4,8,8] | Total encoder downsample = 512x |
| DAC quantizer downsample = [2,2] | Additional 4x from quantizer |
| **Total upsample factor = 2048** | 1 VQ timestep = 2048 audio samples = ~46.4ms at 44.1kHz |
| Slow AR = 1 step per timestep | Generates 1 semantic token via main transformer (36 layers) |
| Fast AR = 10 steps per timestep | Generates 10 codebook indices via fast transformer (4 layers) |

### Token Generation Unit

Each slow-AR step produces one complete "column" of the codes tensor: 1 semantic token + 10 codebook indices. The fast AR runs sequentially within a single slow-AR step (it has its own tiny KV cache of max_seq_len=num_codebooks). One complete column corresponds to ~46.4ms of audio.

## Yield Point Options (Ranked by Feasibility)

### Option 1: Yield from `decode_n_tokens` every N slow-AR steps (RECOMMENDED)

**Where**: Inside the `for i in tqdm(range(num_new_tokens))` loop in `decode_n_tokens()` (line 228).

**Mechanism**: After every N iterations (e.g., N=20, ~928ms of audio), yield the accumulated partial codes back up through the call chain.

**Feasibility**: HIGH
- Each loop iteration produces one complete (num_codebooks+1, 1) column
- Columns are independent -- the slow AR's KV cache is unaffected by yielding
- The fast AR KV cache is reset each step (it operates on just num_codebooks positions)
- No data dependency between yielded partial codes and future generation

**Trade-offs**:
- Requires converting `decode_n_tokens` from a function that returns a tensor to a generator
- Requires converting `generate` from a function that returns a tensor to a generator
- Requires modifying `generate_long` to yield partial responses from within its batch loop
- The refactoring cascades through 3 function levels

### Option 2: Yield from `generate_long` by splitting max_new_tokens into sub-ranges

**Where**: In `generate_long()`, replace the single `generate()` call with multiple calls, each generating N tokens.

**Mechanism**: Call `generate()` with `max_new_tokens=N` repeatedly, feeding back the accumulated context.

**Feasibility**: LOW
- Would require re-encoding the full conversation + previously generated tokens each time
- Extremely expensive: re-runs prefill for every sub-chunk
- KV cache gets reset between calls (current code reinitializes it)
- Breaks the generation flow -- the model needs continuous context

### Option 3: Callback-based approach inside `decode_n_tokens`

**Where**: Pass a callback to `decode_n_tokens` that fires every N tokens.

**Mechanism**: `decode_n_tokens` calls `callback(partial_codes)` every N steps instead of yielding.

**Feasibility**: MEDIUM
- Avoids converting the entire call chain to generators
- The callback could push partial codes into a queue
- But it still requires threading or async coordination
- Less Pythonic than the generator approach
- Harder to test and reason about

### Option 4: Separate producer thread with shared queue

**Where**: `decode_n_tokens` runs in a thread, pushes partial results to a queue.

**Mechanism**: The existing `launch_thread_safe_queue` pattern already uses queues between the generation thread and consumer.

**Feasibility**: MEDIUM
- Already have the queue infrastructure
- But adds complexity inside the generation thread
- Still need to modify `decode_n_tokens` to push partials
- Queue coordination adds latency

## torch.compile Constraints

### What is compiled

From `init_model()` (line 414-427):
```python
if compile:
    decode_one_token = torch.compile(
        decode_one_token,
        backend="inductor",
        mode="reduce-overhead",
        fullgraph=False,
    )
```

**Only `decode_one_token_ar` is compiled.** The functions `decode_n_tokens`, `generate`, and `generate_long` are NOT compiled.

### Impact of partial yielding

**No impact on the compiled function.** The yield points would be in `decode_n_tokens`, which is outside the compiled graph. `decode_one_token_ar` is called as an opaque function from within `decode_n_tokens`'s loop. Adding yield logic between calls to `decode_one_token_ar` does not break the compiled graph because:

1. `decode_one_token_ar` is compiled with `fullgraph=False`, allowing graph breaks
2. The yield happens BETWEEN calls to the compiled function, not within it
3. The compiled function's KV cache state is managed via tensor mutations (in-place updates to `k_cache`/`v_cache`), which persist across yield boundaries
4. `mode="reduce-overhead"` uses CUDA graphs, but these are per-call and don't span across the yield

**Key constraint**: We must NOT yield inside `decode_one_token_ar` itself. The yield must happen in the outer loop.

### CUDA Graph Considerations

With `reduce-overhead` mode, PyTorch records CUDA graphs for `decode_one_token_ar`. These graphs:
- Capture a fixed sequence of CUDA operations
- Replay efficiently on subsequent calls
- Are NOT affected by Python-level yielding between calls
- The input/output tensors remain at fixed memory addresses (critical for CUDA graph replay)

**Risk**: If yielding causes the consumer to run DAC decoding on the same GPU, this could interfere with CUDA graph replay. Mitigation: The existing architecture already handles this -- the generation runs in a separate thread (`launch_thread_safe_queue`), and the consumer decodes on the same device but in a different thread. This is already the case for chunk-level streaming.

## KV Cache Analysis

### Slow AR KV Cache
- Shape: `(1, n_local_heads, max_seq_len, head_dim)` per layer (36 layers)
- Managed via `input_pos` tensor: each decode step writes to `k_cache[:, :, input_pos]`
- `input_pos` increments by 1 each step
- **Yielding does NOT affect the cache**: we're not modifying `input_pos` or the cache state. The Python generator simply suspends execution and resumes exactly where it left off.

### Fast AR KV Cache
- Shape: `(1, fast_n_local_heads, num_codebooks, fast_head_dim)` per fast layer (4 layers)
- `max_seq_len = num_codebooks = 10` (tiny cache)
- Reset implicitly each slow-AR step: the fast AR always starts at `input_pos=0` and writes positions 0..9
- Overwritten completely every slow-AR step, so yielding between slow-AR steps is safe

### Conclusion
Yielding partial results between slow-AR steps has **zero KV cache implications**. The slow AR cache continues to grow naturally, and the fast AR cache is ephemeral per step.

## Recommended Approach

### Convert `decode_n_tokens` to a generator that yields every N tokens

This is the cleanest approach because:
1. It touches the minimal surface area (3 functions)
2. It preserves the compiled `decode_one_token_ar` function unchanged
3. It uses Python's native generator protocol (no threads or queues needed beyond existing infra)
4. KV cache state is preserved naturally across yields
5. The existing `launch_thread_safe_queue` consumer already iterates over `generate_long`'s yields

### Signaling partial vs final

Extend `GenerateResponse` with a `is_partial` field:
```python
@dataclass
class GenerateResponse:
    action: Literal["sample", "next"]
    codes: Optional[torch.Tensor] = None
    text: Optional[str] = None
    is_partial: bool = False  # New: True for sub-chunk yields
```

The consumer can then distinguish:
- `is_partial=True, action="sample"`: decode and stream immediately, don't add to conversation history
- `is_partial=False, action="sample"`: final chunk of a text batch, add to conversation history
- `action="next"`: all samples done

### Choosing N (yield interval)

Each slow-AR token = ~46.4ms of audio. Target sub-chunk size considerations:
- **N=10 tokens = ~464ms**: Very responsive, but codec decode overhead may dominate
- **N=20 tokens = ~928ms**: Good balance -- just under 1 second per yield
- **N=30 tokens = ~1.4s**: Lower overhead, but less streaming benefit
- **Configurable**: Make N a parameter (default 20) so it can be tuned

Recommendation: **N=20** (default), configurable via a `sub_chunk_tokens` parameter.

## Implementation Sketch

### Step 1: Make `decode_n_tokens` a generator

```python
def decode_n_tokens(
    model, cur_token, input_pos, num_new_tokens,
    temperature, top_p, top_k,
    semantic_logit_bias, audio_masks, audio_parts,
    decode_one_token=decode_one_token_ar,
    sub_chunk_tokens: int = 0,  # 0 = no sub-chunking (original behavior)
):
    previous_tokens = torch.zeros(
        (model.config.num_codebooks + 1, RAS_WIN_SIZE),
        dtype=torch.int, device=cur_token.device,
    )
    new_tokens = []
    im_end_id = model.tokenizer.get_token_id(IM_END_TOKEN)

    for i in tqdm(range(num_new_tokens)):
        with sdpa_kernel(SDPBackend.MATH):
            next_token = decode_one_token(
                model=model, x=cur_token, input_pos=input_pos,
                previous_tokens=previous_tokens,
                temperature=temperature, top_p=top_p, top_k=top_k,
                semantic_logit_bias=semantic_logit_bias,
                audio_masks=audio_masks, audio_parts=audio_parts,
            ).clone()

        input_pos += 1
        cur_token = next_token.view(1, model.config.num_codebooks + 1, -1)
        previous_tokens = previous_tokens.roll(-1, dims=1)
        previous_tokens[:, -1] = next_token.view(
            model.config.num_codebooks + 1, -1
        )[:, 0]
        new_tokens.append(next_token)

        # Sub-chunk yield point
        if sub_chunk_tokens > 0 and len(new_tokens) >= sub_chunk_tokens:
            yield torch.cat(new_tokens, dim=1)
            new_tokens = []

        if cur_token[0, 0, -1] == im_end_id:
            break

    del cur_token

    # Yield remaining tokens (could be partial or all tokens if no sub-chunking)
    if new_tokens:
        yield torch.cat(new_tokens, dim=1)
```

### Step 2: Make `generate` a generator

```python
def generate(
    *, model, prompt, max_new_tokens, audio_masks, audio_parts,
    decode_one_token=decode_one_token_ar, num_samples=1,
    sub_chunk_tokens=0, **sampling_kwargs,
):
    # ... (setup code unchanged: cache, bias, input_pos, etc.) ...

    # Prefill
    first_token = prefill_decode(
        model, prompt.view(1, codebook_dim, -1), input_pos,
        temperature, top_p, top_k_val, semantic_logit_bias,
        audio_masks, audio_parts,
    )
    seq[:, T:T+1] = first_token
    input_pos = torch.tensor([T], device=device, dtype=torch.int)

    # Track cumulative position for seq assembly
    write_pos = T + 1

    for partial_codes in decode_n_tokens(
        model, first_token.view(1, codebook_dim, -1), input_pos,
        max_new_tokens - 1, temperature=temperature, top_p=top_p,
        top_k=top_k_val, semantic_logit_bias=semantic_logit_bias,
        audio_masks=audio_masks, audio_parts=audio_parts,
        decode_one_token=decode_one_token,
        sub_chunk_tokens=sub_chunk_tokens,
    ):
        n = partial_codes.size(1)
        seq[:, write_pos:write_pos+n] = partial_codes
        write_pos += n
        yield seq[:, :write_pos]  # yield cumulative seq so far

    del first_token, prompt, empty, input_pos
```

### Step 3: Modify `generate_long` to yield partial responses

```python
# Inside generate_long's batch loop, replace the single generate() call:

first_partial = True
total_generated = 0

for cumulative_seq in generate(
    model=model, prompt=encoded, max_new_tokens=max_new_tokens,
    audio_masks=audio_masks, audio_parts=audio_parts,
    decode_one_token=decode_one_token,
    sub_chunk_tokens=sub_chunk_tokens,
    temperature=temperature, top_p=top_p, top_k=top_k,
):
    # Extract codes from cumulative seq
    codes = cumulative_seq[1:, prompt_length:-1].clone()
    if codes.size(1) == 0:
        continue

    # Determine if this is partial or final
    # (Final will be the last yield from the generator)
    # We yield partial with is_partial=True
    yield GenerateResponse(
        action="sample", codes=codes, text=batch_text, is_partial=True
    )

# After the generate() loop completes, yield the final full codes
# and update conversation history with the complete codes
codes = cumulative_seq[1:, prompt_length:-1].clone()
conversation.append(
    Message(role="assistant", parts=[VQPart(codes=codes.cpu())], ...)
)
yield GenerateResponse(
    action="sample", codes=codes, text=batch_text, is_partial=False
)
```

**Important detail**: The consumer needs to handle partial yields differently. For partial yields, it should decode only the NEW tokens (delta since last yield), not the full cumulative tensor. This means either:

(a) Yield deltas instead of cumulative tensors (simpler for consumer), or
(b) Have the consumer track what it has already decoded

**Recommendation**: Yield deltas from `decode_n_tokens` (as shown in the sketch above -- each yield is only the new batch of tokens, not cumulative). This is simpler and avoids redundant decoding.

### Step 4: Update consumer (TTSInferenceEngine.inference)

```python
# In TTSInferenceEngine.inference():
result: GenerateResponse = wrapped_result.response
if result.action != "next":
    segment = self.get_audio_segment(result)
    
    if crossfader is not None:
        emittable = crossfader.process(segment)
        if emittable is not None and len(emittable) > 0:
            yield InferenceResult(
                code="segment",
                audio=(sample_rate, emittable),
                error=None,
            )
    
    segments.append(segment)
```

The consumer code is **already correct** -- it processes each `GenerateResponse` with `action="sample"` identically regardless of whether it's partial or final. The crossfader handles blending between segments. No changes needed here unless we want to skip crossfading for within-chunk partials (since they're contiguous audio).

### Crossfader Consideration

Within a single text chunk, partial yields produce contiguous audio -- there are no boundary artifacts between sub-chunks. The crossfader is designed for boundaries between TEXT chunks (where the model may have slight discontinuities). Options:

1. **Simple approach**: Let the crossfader handle all segments (including sub-chunk partials). It will crossfade unnecessarily but harmlessly at sub-chunk boundaries. This requires no consumer changes.

2. **Optimized approach**: Skip crossfading for sub-chunk partials (they're contiguous), only crossfade at text-chunk boundaries. This requires the consumer to know `is_partial`.

Recommendation: Start with (1) for simplicity. Optimize to (2) later if crossfade overhead matters.

## Revised Implementation Sketch (Delta-Based)

After further analysis, the cleanest approach is to yield **deltas** (just the newly generated tokens) from `decode_n_tokens`, and have `generate_long` yield partial `GenerateResponse` objects with just the new codes:

```
decode_n_tokens:
  yields (num_codebooks+1, N) tensors every N steps
  
generate (becomes a generator):
  for each partial from decode_n_tokens:
    accumulates into seq tensor
    yields partial codes (delta only): (num_codebooks, N)

generate_long:
  for each partial from generate:
    yield GenerateResponse(action="sample", codes=partial_delta, is_partial=True)
  # After generate exhausts:
  yield final GenerateResponse with accumulated codes + update conversation
```

The consumer side (which already works with one `GenerateResponse` per text chunk) will naturally receive multiple `GenerateResponse` objects per text chunk -- each producing an audio segment that gets crossfaded and streamed.

## Summary of Changes Required

| File | Function | Change |
|------|----------|--------|
| `inference.py` | `GenerateResponse` | Add `is_partial: bool = False` field |
| `inference.py` | `decode_n_tokens` | Convert to generator, yield every N tokens |
| `inference.py` | `generate` | Convert to generator, iterate over `decode_n_tokens` yields |
| `inference.py` | `generate_long` | Iterate over `generate` yields, yield partial responses, track accumulated codes for conversation |
| `inference.py` | `launch_thread_safe_queue` | No change needed (already iterates `generate_long` yields) |
| `__init__.py` | `TTSInferenceEngine.inference` | Minimal change: optionally use `is_partial` to skip crossfade for sub-chunk boundaries |

### Non-Changes (Preserved As-Is)
- `decode_one_token_ar` -- compiled function, untouched
- `init_model` -- no changes
- `DualARTransformer` and KV cache -- no changes
- DAC codec `from_indices` -- no changes
- `StreamingCrossfader` -- no changes needed initially
