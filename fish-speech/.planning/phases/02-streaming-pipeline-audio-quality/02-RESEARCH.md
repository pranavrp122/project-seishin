# Phase 2: Streaming Pipeline & Audio Quality - Research

**Researched:** 2026-04-12
**Domain:** Real-time audio streaming with crossfade stitching, WAV header construction, PCM encoding
**Confidence:** HIGH

## Summary

Phase 2 transforms the current batch-and-concatenate audio pipeline into a streaming crossfade pipeline. The existing code already has the streaming infrastructure (header/segment/final yielding, chunked HTTP via StreamResponse, int16 scaling) but lacks crossfade at chunk boundaries and has a broken WAV header (0-byte data size instead of 0xFFFFFFFF). The core work is: (1) a new `StreamingCrossfader` class that buffers overlap regions and applies equal-power sin^2 blending, (2) WAV header fix for streaming, and (3) wiring the crossfader into `TTSInferenceEngine.inference()`.

The codebase is well-structured for this change. All audio segments pass through a single point (`get_audio_segment()` -> segment collection in `inference()`) where the crossfader can be inserted. The existing `InferenceResult` dataclass and `inference_wrapper()` already handle streaming emission correctly -- segments go out as int16 PCM bytes via the wrapper. No new dependencies are needed; everything uses numpy, which is already imported and used throughout.

**Primary recommendation:** Implement StreamingCrossfader as a stateful class in `fish_speech/inference_engine/`, wire it into `inference()` between `get_audio_segment()` and the segment yield, and replace `wav_chunk_header()` with a struct.pack-based implementation that produces 0xFFFFFFFF sizes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Equal-power sin^2 crossfade applied at every chunk boundary to eliminate clicks/pops/discontinuities
- **D-02:** Crossfade duration 10-20ms (441-882 samples at 44.1kHz)
- **D-03:** Crossfade operates on decoded audio (numpy float32 arrays after PeakFilter), not on VQ tokens
- **D-04:** New class `StreamingCrossfader` that buffers the tail `overlap_samples` from the previous segment and blends with the head of the next segment using equal-power sin^2 curves
- **D-05:** First segment: emit immediately after trimming the tail into the buffer
- **D-06:** Subsequent segments: blend buffered tail with current head, emit blended region + non-overlapping body, buffer new tail
- **D-07:** Final flush: emit the remaining buffered tail when generation completes
- **D-08:** Crossfader state is per-request -- reset between different TTS requests
- **D-09:** Segments yielded to client as they are crossfaded
- **D-10:** First audio segment emitted ASAP after first chunk decodes (TTFA-critical path)
- **D-11:** Each emitted segment is a complete, playable int16 PCM byte sequence
- **D-12:** WAV header uses `0xFFFFFFFF` for both RIFF chunk size and data chunk size
- **D-13:** Replace current `wav_chunk_header()` implementation
- **D-14:** All streaming segments encoded as int16 PCM throughout
- **D-15:** Amplitude scaling uses existing `* 32768` + `.astype(np.int16)` pattern
- **D-16:** PeakFilter stays per-chunk BEFORE crossfade (current behavior)
- **D-17:** Non-streaming final audio path: PeakFilter per-segment before concatenation -- unchanged
- **D-18:** Non-streaming CLI path continues merging VQ codes with torch.cat -- no crossfade needed
- **D-19:** Streaming=false API requests produce final concatenated audio with no behavior change

### Claude's Discretion
- Exact sin^2 crossfade implementation (window functions, sample-level math)
- Internal method names and StreamingCrossfader API surface
- Whether to use overlap-add or overlap-save for the crossfade blending
- Buffer management details (pre-allocation vs dynamic)
- Logging verbosity for streaming segments

### Deferred Ideas (OUT OF SCOPE)
- Acoustic tail prompting (ADVQ-01) -- feeding previous chunk's last ~25 codec frames to next chunk's decoder
- Overlapped DAC decoding with extra context tokens (ADVQ-02)
- Adaptive chunk sizing based on emotion (ADVQ-03)
- KV cache accumulation between chunks (PERF-02)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRM-01 | TTFA < 500ms for typical dialogue lines (50-200 chars) | First segment emitted immediately after first chunk decode; crossfader adds zero latency to first segment (no prior tail to blend). Phase 1 already targets 80-byte first chunks for fast TTFA. |
| STRM-02 | Audio segments yielded to client as each chunk completes | StreamingCrossfader yields blended audio as soon as each segment is processed. Existing generator pipeline already yields InferenceResult per segment. |
| STRM-03 | StreamingCrossfader buffers tail of previous chunk and blends with head of next | Core crossfader architecture: hold back overlap_samples from tail, blend on next segment arrival. See Architecture Patterns section. |
| STRM-04 | WAV header uses 0xFFFFFFFF sizes for streaming unknown length | Replace wave module with struct.pack construction. Byte offsets: RIFF size at offset 4, data size at offset 40. See Code Examples. |
| STRM-05 | Streaming encoding consistent (int16 PCM throughout, no float32 mismatch) | Crossfader operates on float32, emission converts to int16 via existing AMPLITUDE*32768 pattern. Final yield in streaming mode is silently dropped (numpy, not bytes). |
| QUAL-01 | Equal-power crossfade at chunk boundaries eliminates clicks/pops/discontinuities | sin^2 crossfade with fade_in + fade_out = 1.0 at all points (mathematically verified). Operates on post-PeakFilter float32 arrays. |
| QUAL-02 | Crossfade duration tuned to ~10-20ms (441-882 samples at 44.1kHz) | Verified: 882 samples = 20ms, 441 samples = 10ms. Even the smallest possible chunk (5 VQ tokens = 10240 samples) dwarfs the overlap region (2.2% of min audio). |
| QUAL-03 | Audio quality subjectively matches non-streaming output across all emotions | Crossfade preserves energy (sin^2 + cos^2 = 1). PeakFilter applied identically per-chunk. Same DAC decode path. Quality parity achieved by design; subjective testing needed for verification. |
| QUAL-04 | PeakFilter post-FX applied consistently | Already applied per-chunk in `get_audio_segment()` (line 201). Crossfade operates on post-FX audio. No change needed to PeakFilter application -- just document that it stays as-is. |
</phase_requirements>

## Standard Stack

### Core (Already Installed -- Zero Changes)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | 2.4.4 | Crossfade math, sin^2 window, array slicing | Already imported in `__init__.py`. Crossfade is 5-10 lines of numpy. |
| struct | stdlib | WAV header construction with 0xFFFFFFFF | Cleaner than patching wave module output. Single pack call. |
| pedalboard | 0.9.22 | PeakFilter post-FX (unchanged) | Already applied per-chunk in `get_audio_segment()`. No modification. |

### What NOT to Install
| Library | Why NOT |
|---------|---------|
| scipy | Crossfade is trivially done in numpy. scipy.signal is overkill. |
| pydub | Full-file loader, no streaming support. Wrong tool entirely. |
| librosa | Heavy, lazy imports. Already avoided in inference path. |

## Architecture Patterns

### Recommended File Structure
```
fish_speech/inference_engine/
  __init__.py         # TTSInferenceEngine.inference() -- wire crossfader here
  utils.py            # wav_chunk_header() -- replace implementation
  crossfader.py       # NEW: StreamingCrossfader class
  vq_manager.py       # Unchanged
  reference_loader.py # Unchanged
tools/server/
  inference.py        # inference_wrapper() -- no changes needed
  api_utils.py        # inference_async() -- no changes needed
  views.py            # No changes needed
```

### Pattern 1: StreamingCrossfader Class

**What:** Stateful object that buffers the tail of each audio segment and blends it with the head of the next, yielding crossfaded audio as it goes.

**When to use:** Instantiated once per streaming TTS request inside `inference()`, used for the duration of the segment loop.

**API design:**
```python
class StreamingCrossfader:
    def __init__(self, overlap_samples: int = 882):
        """
        Args:
            overlap_samples: Number of samples to overlap between segments.
                882 = 20ms at 44.1kHz. Range: 441-882 (10-20ms).
        """
        self._overlap = overlap_samples
        self._tail_buffer: np.ndarray | None = None
        # Pre-compute crossfade curves once
        t = np.linspace(0, 1, overlap_samples, dtype=np.float32)
        self._fade_in = np.sin(t * np.pi / 2) ** 2
        self._fade_out = np.cos(t * np.pi / 2) ** 2

    def process(self, segment: np.ndarray) -> np.ndarray | None:
        """Feed a new decoded+filtered segment. Returns crossfaded audio to emit,
        or None if segment was too short (shouldn't happen with normal chunks)."""
        ...

    def flush(self) -> np.ndarray | None:
        """Emit any remaining buffered tail. Call after last segment."""
        ...
```

**Internal logic for `process()`:**
```python
def process(self, segment: np.ndarray) -> np.ndarray | None:
    if len(segment) < self._overlap:
        # Edge case: segment shorter than overlap (very unlikely with DAC)
        # Append to tail buffer or emit as-is
        if self._tail_buffer is not None:
            result = np.concatenate([self._tail_buffer, segment])
            self._tail_buffer = None
            return result
        return segment

    if self._tail_buffer is None:
        # First segment: emit body, buffer tail
        body = segment[:-self._overlap]
        self._tail_buffer = segment[-self._overlap:].copy()
        return body if len(body) > 0 else None

    # Subsequent segments: blend buffered tail with current head
    head = segment[:self._overlap]
    blended = self._tail_buffer * self._fade_out + head * self._fade_in

    # Body is everything between head and tail
    body = segment[self._overlap:-self._overlap]

    # Buffer new tail
    self._tail_buffer = segment[-self._overlap:].copy()

    # Emit blended region + body
    return np.concatenate([blended, body])
```

### Pattern 2: WAV Header with struct.pack

**What:** Replace the Python `wave` module approach with direct struct.pack for streaming-compatible WAV headers.

**Why:** The `wave` module writes 0 for data size (no audio written). We need 0xFFFFFFFF. Direct struct.pack is cleaner than post-patching the wave output.

```python
import struct

def wav_chunk_header(
    sample_rate: int = 44100, bit_depth: int = 16, channels: int = 1
) -> bytes:
    byte_rate = sample_rate * channels * (bit_depth // 8)
    block_align = channels * (bit_depth // 8)

    header = struct.pack('<4sI4s', b'RIFF', 0xFFFFFFFF, b'WAVE')
    header += struct.pack('<4sIHHIIHH',
        b'fmt ', 16, 1, channels, sample_rate, byte_rate, block_align, bit_depth)
    header += struct.pack('<4sI', b'data', 0xFFFFFFFF)
    return header
```

### Pattern 3: Crossfader Integration in inference()

**What:** Wire StreamingCrossfader into the existing segment loop.

**Where:** `TTSInferenceEngine.inference()` in `fish_speech/inference_engine/__init__.py`

```python
# Current code (lines 89-124):
segments = []
while True:
    # ... get wrapped_result from queue ...
    if result.action != "next":
        segment = self.get_audio_segment(result)
        if req.streaming:
            yield InferenceResult(code="segment", audio=(sample_rate, segment), error=None)
        segments.append(segment)
    else:
        break

# After Phase 2 (streaming path):
crossfader = StreamingCrossfader(overlap_samples=882) if req.streaming else None
segments = []
while True:
    # ... get wrapped_result from queue ...
    if result.action != "next":
        segment = self.get_audio_segment(result)
        if req.streaming and crossfader is not None:
            emittable = crossfader.process(segment)
            if emittable is not None and len(emittable) > 0:
                yield InferenceResult(code="segment", audio=(sample_rate, emittable), error=None)
        segments.append(segment)
    else:
        break

# After loop, flush remaining tail for streaming
if req.streaming and crossfader is not None:
    tail = crossfader.flush()
    if tail is not None and len(tail) > 0:
        yield InferenceResult(code="segment", audio=(sample_rate, tail), error=None)
```

### Anti-Patterns to Avoid
- **Crossfading VQ tokens:** Tokens are discrete codebook indices. Blending them is meaningless. Always crossfade decoded float32 audio.
- **Re-applying PeakFilter after crossfade:** The overlap region is 10-20ms. Re-filtering would double-process those samples. PeakFilter is already applied in `get_audio_segment()`.
- **Modifying inference_wrapper for crossfade:** The crossfade belongs in the engine, not the HTTP layer. The wrapper should remain a thin bytes-conversion layer.
- **Using the `wave` module for streaming headers:** The `wave` module doesn't support setting arbitrary chunk sizes. Use struct.pack directly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WAV format parsing | Custom byte manipulation | `struct.pack` with known WAV layout | WAV is a well-specified 44-byte header. struct.pack is the standard approach. |
| Audio resampling | Manual interpolation | N/A (not needed -- DAC outputs at 44.1kHz natively) | Resampling is complex. Fortunately DAC's native rate matches the streaming rate. |
| Crossfade curves | Lookup tables or manual interpolation | `np.sin()` / `np.cos()` pre-computed once | numpy vectorized trig is fast enough for 441-882 samples. |

**Key insight:** The entire crossfade operation is ~10 lines of numpy. The complexity is in the buffering state machine, not the math.

## Common Pitfalls

### Pitfall 1: Off-by-One in Overlap Boundaries
**What goes wrong:** The crossfaded audio has a 1-sample gap or 1-sample overlap, causing a faint click at every boundary.
**Why it happens:** Confusing inclusive vs exclusive indexing when slicing head/body/tail from each segment.
**How to avoid:** The key invariant is: `len(blended) + len(body) + len(new_tail) == len(segment)`. Assert this in development. The blended region replaces the head (first `overlap` samples), body is the middle, tail is the last `overlap` samples.
**Warning signs:** Faint periodic clicks at regular intervals matching chunk duration.

### Pitfall 2: Final Tail Not Flushed
**What goes wrong:** The last 10-20ms of the final segment is never emitted because it's sitting in the crossfader's tail buffer.
**Why it happens:** Forgetting to call `flush()` after the generation loop ends.
**How to avoid:** Always call `crossfader.flush()` after the while loop breaks. The flush emits the buffered tail as-is (no next segment to blend with).
**Warning signs:** Audio consistently truncated at the end. Last syllable cut short.

### Pitfall 3: Non-Streaming Path Accidentally Gets Crossfade
**What goes wrong:** The non-streaming API path (streaming=False) starts producing crossfaded audio, changing behavior.
**Why it happens:** Applying the crossfader unconditionally to all segments instead of gating on `req.streaming`.
**How to avoid:** Only instantiate `StreamingCrossfader` when `req.streaming is True`. The non-streaming path continues to use raw `np.concatenate(segments)`. Per D-19, no behavior change for non-streaming.
**Warning signs:** Non-streaming API responses change byte-for-byte from pre-Phase-2.

### Pitfall 4: Float32 vs Int16 Confusion in Streaming
**What goes wrong:** Audio sounds like white noise or is extremely quiet.
**Why it happens:** The crossfader emits float32 arrays (range -1.0 to 1.0). The wrapper multiplies by AMPLITUDE=32768 and casts to int16. If crossfaded audio is already scaled to int16 range, the double-scaling produces overflow or clipping.
**How to avoid:** Crossfader works entirely in float32 space. Int16 conversion happens ONLY in `inference_wrapper()` at the `case "segment"` branch, which already does `(audio * AMPLITUDE).astype(np.int16).tobytes()`.
**Warning signs:** Audio clipping, distortion, or white noise in streaming but not non-streaming.

### Pitfall 5: WAV Header Uses Wrong Byte Order
**What goes wrong:** Audio players reject the stream or play garbage.
**Why it happens:** WAV uses little-endian. Using `>` (big-endian) in struct.pack would produce an invalid header.
**How to avoid:** Always use `<` (little-endian) format character in struct.pack for WAV headers.
**Warning signs:** "Unsupported audio format" errors in media players.

### Pitfall 6: Crossfader State Leaking Between Requests
**What goes wrong:** The first segment of a new request contains blended audio from the tail of the previous request.
**Why it happens:** Reusing a single crossfader instance across requests.
**How to avoid:** Create a new `StreamingCrossfader()` instance inside `inference()` per request (per D-08). Since `inference()` is a generator that runs per-request, this is natural -- just instantiate at function scope.
**Warning signs:** First segment of a request sounds like it has a different voice/text blended in.

## Code Examples

Verified patterns from codebase analysis:

### Equal-Power Sin^2 Crossfade (numpy)
```python
# Source: Mathematical verification (sin^2 + cos^2 = 1, confirmed numerically)
import numpy as np

overlap_samples = 882  # 20ms at 44.1kHz
t = np.linspace(0, 1, overlap_samples, dtype=np.float32)
fade_in = np.sin(t * np.pi / 2) ** 2   # 0.0 -> 1.0 (equal power)
fade_out = np.cos(t * np.pi / 2) ** 2  # 1.0 -> 0.0 (equal power)

# Blend: previous_tail * fade_out + current_head * fade_in
# Energy is constant: fade_in + fade_out = 1.0 at every sample
blended = previous_tail * fade_out + current_head * fade_in
```

**Note:** sin^2 and Hann window are mathematically equivalent for crossfade: `sin^2(t*pi/2) = 0.5*(1 - cos(pi*t))`. The STACK.md mentions Hann, the CONTEXT.md says sin^2 -- they produce identical results.

### Streaming WAV Header (struct.pack)
```python
# Source: WAV specification (http://soundfile.sapp.org/doc/WaveFormat/)
# Verified: produces correct 44-byte header with 0xFFFFFFFF streaming sizes
import struct

def wav_chunk_header(
    sample_rate: int = 44100, bit_depth: int = 16, channels: int = 1
) -> bytes:
    byte_rate = sample_rate * channels * (bit_depth // 8)
    block_align = channels * (bit_depth // 8)

    header = struct.pack('<4sI4s', b'RIFF', 0xFFFFFFFF, b'WAVE')
    header += struct.pack('<4sIHHIIHH',
        b'fmt ', 16, 1, channels, sample_rate, byte_rate, block_align, bit_depth)
    header += struct.pack('<4sI', b'data', 0xFFFFFFFF)
    return header

# Current broken header (for reference):
#   RIFF size = 36 (0x00000024) -- should be 0xFFFFFFFF
#   data size =  0 (0x00000000) -- should be 0xFFFFFFFF
```

### Current Segment Flow (for reference)
```python
# Source: fish_speech/inference_engine/__init__.py lines 89-144
# This is what gets modified:

# get_audio_segment() returns float32 numpy array (post-PeakFilter)
segment = self.get_audio_segment(result)  # float32, range ~[-1.0, 1.0]

# Streaming: yield as InferenceResult
if req.streaming:
    yield InferenceResult(code="segment", audio=(sample_rate, segment), error=None)

# inference_wrapper() converts: (segment * 32768).astype(np.int16).tobytes()
# inference_async() filters: isinstance(chunk, bytes) then yield
```

### Byte Layout of Current vs Fixed WAV Header
```
Offset  Current                    Fixed (Phase 2)
------  -------------------------  -------------------------
0x0000  RIFF                       RIFF
0x0004  24 00 00 00 (size=36)      FF FF FF FF (streaming)
0x0008  WAVE                       WAVE
0x000C  fmt  10 00 00 00           fmt  10 00 00 00
0x0014  01 00 01 00                01 00 01 00
0x0018  44 AC 00 00 (44100Hz)      44 AC 00 00 (44100Hz)
0x001C  88 58 01 00 (88200 B/s)    88 58 01 00 (88200 B/s)
0x0020  02 00 10 00                02 00 10 00
0x0024  data                       data
0x0028  00 00 00 00 (size=0)       FF FF FF FF (streaming)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `np.concatenate` with no overlap | Equal-power crossfade at boundaries | Standard since early audio processing | Eliminates clicks/pops at chunk boundaries |
| Python `wave` module for streaming headers | Direct struct.pack with 0xFFFFFFFF | WAV spec has always supported this | Enables proper streaming playback in media players |
| Full-file generation then send | Per-chunk streaming with crossfade | Common in production TTS (Qwen3-TTS, F5-TTS) | Reduces TTFA from seconds to <500ms |

## Critical Implementation Details

### Data Flow (Streaming Path)
```
generate_long() yields GenerateResponse(codes=...)
    |
    v
get_audio_segment(result)     # VQ decode + PeakFilter -> float32 numpy
    |
    v
StreamingCrossfader.process() # Buffer tail, blend head, emit crossfaded float32
    |
    v
yield InferenceResult(code="segment", audio=(sr, crossfaded_float32))
    |
    v
inference_wrapper()           # (float32 * 32768).astype(int16).tobytes()
    |
    v
inference_async()             # isinstance(chunk, bytes) -> yield
    |
    v
StreamResponse (HTTP chunked transfer)
```

### Data Flow (Non-Streaming Path) -- UNCHANGED
```
generate_long() yields GenerateResponse(codes=...)
    |
    v
get_audio_segment(result)     # VQ decode + PeakFilter -> float32 numpy
    |
    v
segments.append(segment)      # No crossfade, no streaming yield
    |
    v
np.concatenate(segments)      # Raw concatenation (same as before)
    |
    v
yield InferenceResult(code="final", audio=(sr, float32_array))
    |
    v
inference_wrapper()           # yield float32 numpy array as-is
    |
    v
views.py: sf.write(buffer, array, sr)  # soundfile handles float->PCM
```

### Key Numerical Facts
- Sample rate: 44100 Hz (DAC native, `self.decoder_model.sample_rate`)
- Overlap at 20ms: 882 samples
- Overlap at 10ms: 441 samples
- Each VQ token: 2048 audio samples (~46.4ms)
- Minimum chunk audio (5 tokens): 10240 samples (~232ms) -- overlap is 2.2% of this
- Typical chunk audio (50 tokens): 102400 samples (~2.3s) -- overlap is 0.09% of this
- AMPLITUDE constant: 32768 (int16 max + 1)
- WAV header: 44 bytes total

### Files Modified (Exhaustive List)
1. `fish_speech/inference_engine/crossfader.py` -- NEW FILE: StreamingCrossfader class
2. `fish_speech/inference_engine/__init__.py` -- Wire crossfader into `inference()` streaming path
3. `fish_speech/inference_engine/utils.py` -- Replace `wav_chunk_header()` implementation

### Files NOT Modified
- `tools/server/inference.py` -- No changes (int16 conversion already correct)
- `tools/server/api_utils.py` -- No changes (async wrapper already filters bytes)
- `tools/server/views.py` -- No changes (streaming and non-streaming paths work as-is)
- `fish_speech/models/text2semantic/inference.py` -- No changes (generate_long unchanged)
- `fish_speech/inference_engine/vq_manager.py` -- No changes (decode unchanged)

## Open Questions

1. **Optimal overlap duration within 10-20ms range**
   - What we know: 10ms (441 samples) is the minimum, 20ms (882 samples) is the maximum per D-02. Both are well below auditory perception threshold.
   - What's unclear: Whether 10ms is sufficient or 20ms produces audibly better results with DAC's specific decoder artifacts.
   - Recommendation: Start at 882 samples (20ms) as the default. This is the safer choice -- the overhead is negligible (0.09-2.2% of chunk audio) and provides more blending room for DAC boundary artifacts. Can tune down to 441 if needed.

2. **Whether the streaming `final` yield serves any purpose**
   - What we know: In streaming mode, `inference_wrapper()` yields `result.audio[1]` for the `final` case (a float32 numpy array). `inference_async()` filters `isinstance(chunk, bytes)`, so this numpy array is silently dropped.
   - What's unclear: Whether any consumer depends on the `final` yield in streaming mode.
   - Recommendation: Keep the `final` yield as-is for backward compatibility. It's harmless (silently dropped) and some future consumer might want the complete audio. The crossfaded segments already provide complete coverage.

## Sources

### Primary (HIGH confidence)
- Fish Speech codebase: direct code analysis of all files in the modification path
- WAV specification: verified header byte layout and 0xFFFFFFFF semantics
- NumPy: verified sin^2 + cos^2 = 1.0 numerically for crossfade energy preservation
- Phase 1 implementation: confirmed `split_text_into_chunks()` and `generate_long()` integration

### Secondary (MEDIUM confidence)
- Qwen3-TTS-streaming: Hann crossfade at 512 samples/24kHz (~21ms) in production
- DAC PR #96: equal-power crossfade at hop_length overlap for boundary smoothing
- `.planning/research/SUMMARY.md`: synthesized findings from 7 research agents

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Zero new dependencies, all existing numpy/struct
- Architecture: HIGH - Single insertion point confirmed, clear data flow traced end-to-end
- Pitfalls: HIGH - All identified from direct code analysis, not theoretical
- Crossfade math: HIGH - Numerically verified, well-established DSP technique

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable domain -- audio crossfade techniques don't change)
