---
phase: 03-sub-chunk-audio-streaming
plan: 01
subsystem: text2semantic-inference
tags: [streaming, generators, sub-chunk, token-yielding]
dependency_graph:
  requires: []
  provides: [generator-decode-n-tokens, generator-generate, generator-generate-long, sub-chunk-tokens-param, is-partial-flag]
  affects: [inference-engine, tts-api]
tech_stack:
  added: []
  patterns: [generator-yielding, cumulative-tensor-assembly]
key_files:
  created: []
  modified:
    - fish_speech/utils/schema.py
    - fish_speech/models/text2semantic/inference.py
    - fish_speech/inference_engine/__init__.py
decisions:
  - Partial yields use cumulative codes (not deltas) for grow-and-redecode compatibility
  - im_end token stripping (:-1) only on final yield, not partial yields
  - sub_chunk_tokens only active when streaming=True (enforced in send_Llama_request)
metrics:
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 3 Plan 1: Generator-Converted Token Yielding Summary

Generator-converted decode_n_tokens/generate/generate_long chain that yields partial VQ token tensors every N tokens via sub_chunk_tokens parameter, with is_partial flag on GenerateResponse for consumer differentiation.

## Changes Made

### Task 1: Add sub_chunk_tokens parameter and is_partial field

Three files received parameter/field additions:

1. **fish_speech/utils/schema.py** -- Added `sub_chunk_tokens: Annotated[int, Field(ge=0, le=100)] = 0` to `ServeTTSRequest`. Default 0 means no sub-chunking (backward compatible). Valid range 0-100.

2. **fish_speech/models/text2semantic/inference.py** -- Added `is_partial: bool = False` field to the `GenerateResponse` dataclass. Defaults to False so all existing consumers are unaffected.

3. **fish_speech/inference_engine/__init__.py** -- Threaded `sub_chunk_tokens` through `send_Llama_request` dict with guard: `sub_chunk_tokens=req.sub_chunk_tokens if req.streaming else 0`. Only active when streaming is True.

### Task 2: Convert decode_n_tokens and generate to generators

Four changes within `fish_speech/models/text2semantic/inference.py`:

**A. decode_n_tokens** -- Converted from return-based to yield-based. Added `sub_chunk_tokens: int = 0` parameter. When `sub_chunk_tokens > 0`, yields accumulated tokens every N steps then resets the accumulator. When `sub_chunk_tokens=0`, yields once at the end (identical to old `return`). The `decode_one_token_ar` compiled function is NOT modified.

**B. generate** -- Converted from return-based to yield-based. Added `sub_chunk_tokens: int = 0` parameter. Iterates over `decode_n_tokens` generator, assembling partial codes into `seq` via cumulative `write_pos` tracking, and yields `seq[:, :write_pos]` after each sub-chunk.

**C. generate_long** -- Added `sub_chunk_tokens: int = 0` parameter. Iterates over `generate()` as a generator. When `sub_chunk_tokens > 0`, yields `GenerateResponse(action="sample", is_partial=True)` for each partial with cumulative codes (`cumulative_seq[1:, prompt_length:]` -- no im_end stripping). After generation completes, yields final `GenerateResponse(action="sample", is_partial=False)` with `y[1:, prompt_length:-1]` (im_end stripped).

**D. Unmodified paths** -- `decode_one_token_ar` (compiled function): untouched. `launch_thread_safe_queue` worker: unchanged, receives `sub_chunk_tokens` via `**kwargs` passthrough. CLI `main()`: unchanged, doesn't pass `sub_chunk_tokens` so defaults to 0.

## Key Design Decisions

1. **Cumulative codes, not deltas**: Partial yields contain ALL codes generated so far for the current text batch. The consumer (Plan 02) needs cumulative codes for grow-and-redecode audio streaming.

2. **im_end stripping only on final yield**: Partial yields use `cumulative_seq[1:, prompt_length:]` because im_end hasn't been generated yet. Final yield uses `y[1:, prompt_length:-1]` to strip im_end as before.

3. **sub_chunk_tokens gated on streaming**: In `send_Llama_request`, the value is forced to 0 when `req.streaming` is False, preventing accidental sub-chunking in non-streaming mode.

4. **Always a generator**: `decode_n_tokens` and `generate` are always generators (they use `yield`). When `sub_chunk_tokens=0`, they each yield exactly once, making them behaviorally equivalent to the old return-based versions.

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

All checks passed:
- `ServeTTSRequest(text='test').sub_chunk_tokens == 0` -- backward compat
- `GenerateResponse(action='sample').is_partial == False` -- default is_partial
- `inspect.isgeneratorfunction(decode_n_tokens)` -- generator conversion
- `'yield' in inspect.getsource(generate)` -- generate is a generator
- `sub_chunk_tokens` in signatures of all three functions
- `is_partial=True` in partial yields, `is_partial=False` in final yield
- `for partial_codes in decode_n_tokens(...)` in generate
- `for cumulative_seq in generate(...)` in generate_long
- `decode_one_token_ar` lines 115-200 completely untouched
- All three files pass `ast.parse()` syntax check

## Known Stubs

None -- all code paths are fully wired.

## Self-Check: PASSED
