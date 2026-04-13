---
phase: 02-post-fx-chain
reviewed: 2026-04-13T15:10:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - fish_speech/utils/post_fx.py
  - fish_speech/inference_engine/__init__.py
  - tests/test_post_fx.py
  - tools/tts_baseline/generate_corpus.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-13T15:10:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the HumanismPostFX audio processing chain (`post_fx.py`), its integration into the TTS inference engine (`__init__.py`), its test suite (`test_post_fx.py`), and the corpus generation tool (`generate_corpus.py`).

The PostFX chain is well-structured with clean separation between the pedalboard-based effects and the numpy saturation stage. The streaming state management (reset on first call, stateful thereafter) correctly uses pedalboard's `reset` parameter. The safety clipper at -0.1dB combined with the final `np.clip` provides defense-in-depth against out-of-range output.

Three warnings and three informational findings. The most impactful warning is the DC offset introduced by asymmetric saturation (~2.5% of peak), which can accumulate downstream in concatenated audio or cause audible artifacts through speakers with poor DC handling. The unhandled truncated-response case in `generate_corpus.py` could crash the tool. No critical security issues found.

## Warnings

### WR-01: Asymmetric saturation introduces DC offset without compensation

**File:** `fish_speech/utils/post_fx.py:166-167`
**Issue:** The quadratic term `k * audio[mask] ** 2` added to negative half-cycles produces a net positive DC offset in the output signal. Measured at ~2.5% of peak amplitude with `saturation_intensity=1.0`. While individually small, this DC offset: (a) accumulates across concatenated streaming segments, (b) wastes headroom under the safety clipper, and (c) can cause audible clicks at segment boundaries when segments have different DC offsets (e.g., saturation applied to varying signal levels across chunks).

**Fix:** Subtract the running DC bias after saturation. A simple approach:
```python
def _apply_saturation(self, audio: np.ndarray, intensity: float) -> np.ndarray:
    drive = 1.0 + intensity * 2.0
    k = intensity * 0.1

    driven = drive * audio
    saturated = np.tanh(driven)

    mask = audio < 0
    saturated[mask] += k * audio[mask] ** 2

    # Remove DC offset introduced by asymmetric processing
    saturated -= np.mean(saturated)

    return saturated
```
Note: `np.mean` on a single chunk is a coarse estimate. For streaming, a leaky integrator (exponential moving average) would track DC drift more smoothly, but the per-chunk mean subtraction is sufficient given the safety clip downstream.

### WR-02: PostFXConfig accepts out-of-range intensity values without validation

**File:** `fish_speech/utils/post_fx.py:34-45`
**Issue:** `PostFXConfig` is a plain dataclass with no validation. Values outside the documented `[0.0, 1.0]` range are silently accepted. While the code currently only uses `PostFXConfig()` with defaults, this is a public API (imported in `__init__.py` and documented in the module docstring). An intensity of `2.0` doubles the documented effect (e.g., -12dB de-ess instead of -6dB), and negative values bypass the `> 0` guard but would produce inverted effects if that guard were changed. This is a latent bug surface if the config is ever exposed to external callers or configuration files.

**Fix:** Add a `__post_init__` validator:
```python
@dataclass
class PostFXConfig:
    eq_low_intensity: float = 1.0
    eq_high_intensity: float = 1.0
    compression_intensity: float = 1.0
    deess_intensity: float = 1.0
    saturation_intensity: float = 1.0

    def __post_init__(self):
        for field_name in (
            "eq_low_intensity", "eq_high_intensity",
            "compression_intensity", "deess_intensity",
            "saturation_intensity",
        ):
            val = getattr(self, field_name)
            if not (0.0 <= val <= 1.0):
                raise ValueError(
                    f"{field_name} must be in [0.0, 1.0], got {val}"
                )
```

### WR-03: Unhandled ValueError on truncated HTTP response in generate_corpus.py

**File:** `tools/tts_baseline/generate_corpus.py:89-95`
**Issue:** If the HTTP streaming response is truncated (network timeout, server crash, partial write), `pcm_data` may have an odd number of bytes. The `np.frombuffer(pcm_data, dtype=np.int16)` call on line 95 raises `ValueError: buffer size must be a multiple of element size` in this case. The function already handles the empty-data case (line 90) but not the odd-length case.

**Fix:** Truncate to even length before parsing:
```python
pcm_data = raw_bytes[44:]
if len(pcm_data) < 2:
    print(f"    ERROR: Insufficient PCM data for {clip_id}")
    return None

# Ensure even byte count (truncated responses may have trailing byte)
if len(pcm_data) % 2 != 0:
    pcm_data = pcm_data[:-1]

samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
```

## Info

### IN-01: Non-sub-chunk path passes potentially empty audio to post_fx without length check

**File:** `fish_speech/inference_engine/__init__.py:172`
**Issue:** In the backward-compatible (non-sub-chunk) path at line 172, `self.get_audio_segment(result)` is passed directly to `post_fx.process()` without a `len > 0` check, unlike the sub-chunk paths (lines 124, 155). While pedalboard handles empty arrays gracefully (returns empty array), this is an inconsistency in defensive coding patterns within the same function. If the DAC decoder ever returns a zero-length segment, the segment would be appended to `segments` (line 181) and later concatenated into the final audio, introducing a no-op entry.

**Fix:** Add a guard consistent with the sub-chunk paths:
```python
segment = self.get_audio_segment(result)
if len(segment) > 0:
    segment = post_fx.process(segment, sample_rate)
    # ... rest of crossfader logic
```

### IN-02: Magic number 1764 for overlap samples in sub-chunk final path

**File:** `fish_speech/inference_engine/__init__.py:157`
**Issue:** The overlap size `1764` is hardcoded on line 157, while the crossfader is constructed with `overlap_samples=1764` on line 86. These are the same value but expressed as separate literals, making it easy for them to drift apart during future changes. The value 1764 = 44100 * 0.04 (40ms at 44.1kHz) is meaningful but not documented at the usage site.

**Fix:** Extract to a named constant or derive from the crossfader:
```python
OVERLAP_SAMPLES = 1764  # 40ms at 44100Hz

crossfader = StreamingCrossfader(overlap_samples=OVERLAP_SAMPLES) if req.streaming else None
# ...
overlap = OVERLAP_SAMPLES
```

### IN-03: Byte string concatenation in streaming loop

**File:** `tools/tts_baseline/generate_corpus.py:82-84`
**Issue:** `raw_bytes += chunk` inside the streaming loop creates a new bytes object on each iteration due to Python's immutable bytes type. For a typical TTS response (5-30 seconds of 16-bit 44.1kHz audio = 440KB-2.6MB), this is negligible. Flagging only for awareness -- not a practical concern at this corpus size, and a `bytearray` would be the fix if it ever mattered.

**Fix:** No action needed at current scale. If corpus sizes grow significantly:
```python
raw_chunks = []
for chunk in response.iter_content(chunk_size=None):
    raw_chunks.append(chunk)
    if t_first is None and sum(len(c) for c in raw_chunks) > 44:
        t_first = time.time()
raw_bytes = b"".join(raw_chunks)
```

---

_Reviewed: 2026-04-13T15:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
