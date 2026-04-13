# Phase 2: Post-FX Chain - Research

**Researched:** 2026-04-13
**Domain:** Real-time audio post-processing with Spotify Pedalboard (IIR EQ, compression, saturation, limiting)
**Confidence:** HIGH

## Summary

This phase adds a professional vocal processing chain to every TTS utterance using Spotify's Pedalboard library (already installed at v0.9.22) and a custom numpy saturation stage. The chain order is: de-ess, EQ (low-shelf + high-shelf), compress, saturate, limit -- matching the industry-standard vocal chain decided in CONTEXT.md.

The single most critical technical finding is **pedalboard's `reset` parameter behavior**: `__call__()` and `process()` are identical methods, and both default to `reset=True`, which clears all IIR filter state between invocations. For streaming, each chunk must be processed with `board.process(chunk, sr, reset=False)` to maintain compressor envelope and EQ filter state across chunk boundaries. The current codebase uses `self._post_fx(audio, sr)` which is `__call__` with default `reset=True` -- this is safe for a single PeakFilter but would destroy compressor state if upgraded in-place.

A secondary critical finding is that **pedalboard's `Limiter` normalizes audio** (confirmed by GitHub issue #282) -- it contains two internal compressors plus a hard clipper at 0dB, which causes audio to be scaled up to [-1.0, 1.0] even when peaks are well below 0dB. For a safety limiter that only prevents clipping without altering quiet signals, use `Clipping(threshold_db=-0.1)` instead.

**Primary recommendation:** Create a `HumanismPostFX` class wrapping a Pedalboard chain with `reset=False` streaming, custom numpy asymmetric saturation between the pedalboard chain and the safety clipper, and per-effect intensity parameters as a dataclass. Instantiate per-request in the inference loop (not as a class variable).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Effect chain order**: De-ess -> EQ -> Compress -> Saturate -> Limiter
- **Streaming state persistence (WARM-07)**: Use pedalboard's stateful `process()` method, keeping the Pedalboard instance alive per inference request
- **Code architecture**: Create `HumanismPostFX` class in `fish_speech/utils/post_fx.py`, replace `_post_fx` usage in TTSInferenceEngine
- **Intensity parameter architecture (WARM-08)**: Dataclass with per-effect 0.0-1.0 floats, linear interpolation per effect type
- **De-essing (WARM-04)**: Static parametric notch filter at 6.5kHz using PeakFilter with negative gain
- **Saturation (WARM-05)**: Custom numpy implementation -- tanh(x) for positive, tanh(x) + k*x^2 for negative, applied outside pedalboard chain
- **A/B testing**: Re-generate Phase 1 corpus prompts with FX enabled, run existing analysis scripts, plus manual listening
- **Existing PeakFilter disposition**: Replace the existing PeakFilter(3500Hz, +1.5dB, Q=0.7) with the new chain

### Claude's Discretion
No items marked for discretion -- all gray areas were resolved.

### Deferred Ideas (OUT OF SCOPE)
- Dynamic sidechain de-essing (better for varying sibilance but too complex for v1)
- Room tone / convolution IR (deferred to v3+ ENHC-01)
- Micro-pitch jitter (deferred to v3+ ENHC-02)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WARM-01 | Low-shelf EQ at 250Hz adds body/warmth | Pedalboard `LowShelfFilter(cutoff_frequency_hz=250, gain_db=3.0, q=0.7)` -- verified available in v0.9.22 |
| WARM-02 | High-shelf at 8kHz adds subtle air/shimmer | Pedalboard `HighShelfFilter(cutoff_frequency_hz=8000, gain_db=2.0, q=0.7)` -- verified available |
| WARM-03 | Gentle compression (2:1, -20dB threshold) evens dynamics | Pedalboard `Compressor(threshold_db=-20, ratio=2.0, attack_ms=10.0, release_ms=100)` -- verified; attack/release not in req, use vocal defaults |
| WARM-04 | De-essing reduces sibilance (narrow cut at 6.5kHz) | Pedalboard `PeakFilter(cutoff_frequency_hz=6500, gain_db=-6.0, q=4.0)` -- high Q for narrow notch, negative gain for cut |
| WARM-05 | Asymmetric soft saturation (tanh + quadratic) | Custom numpy: positive half `tanh(drive * x)`, negative half `tanh(drive * x) + k * x^2`. k in [0.05, 0.15] range |
| WARM-06 | Safety limiter prevents clipping | `Clipping(threshold_db=-0.1)` preferred over `Limiter` due to normalization issue (GitHub #282) |
| WARM-07 | Streaming compatibility (no state-reset artifacts) | `board.process(chunk, sr, reset=False)` maintains IIR state; per-request instance lifetime |
| WARM-08 | Each effect has 0.0-1.0 intensity parameter | Dataclass with per-effect floats; rebuild Pedalboard chain when params change; linear interpolation |
</phase_requirements>

## Standard Stack

### Core (Already Installed -- No Changes)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pedalboard | 0.9.22 | EQ, compression, de-essing, limiting | Already in pyproject.toml. Built-in `LowShelfFilter`, `HighShelfFilter`, `PeakFilter`, `Compressor`, `Clipping` cover 5 of 6 effects |
| numpy | 2.4.4 | Asymmetric saturation waveshaping | Already used everywhere. `np.tanh()` + quadratic for even-harmonic generation |

### What NOT to Install
| Library | Why NOT |
|---------|---------|
| scipy | Only needed for ADAA anti-aliasing on saturation. At low drive (k=0.05-0.15), aliasing is inaudible at 44.1kHz. Overkill. |
| pydub | Full-file loading, not streaming-compatible |
| noisereduce | Not in requirements; adds FFT overhead per chunk |

**Installation:** No new packages required.

**Version verification:**
- pedalboard: 0.9.22 (latest, verified via `pip index versions`)
- numpy: 2.4.4 (installed, verified via `pip show`)

## Architecture Patterns

### Recommended Project Structure
```
fish_speech/
  utils/
    post_fx.py           # NEW: HumanismPostFX class + PostFXConfig dataclass
  inference_engine/
    __init__.py           # MODIFY: replace _post_fx class var with per-request HumanismPostFX
    crossfader.py         # UNCHANGED
tools/
  tts_baseline/
    generate_corpus.py    # MODIFY: add post-fx A/B generation mode
    analyze_f0.py         # UNCHANGED (reuse for comparison)
    analyze_pauses.py     # UNCHANGED (reuse for comparison)
```

### Pattern 1: Per-Request Stateful Pedalboard
**What:** Create a new `HumanismPostFX` instance for each inference request, call `process(chunk, sr, reset=False)` for each streaming segment.
**When to use:** Always for streaming mode. For non-streaming, a single `__call__` with `reset=True` (the default) is fine but using the same pattern keeps code uniform.
**Why:** The current `_post_fx` is a class-level `Pedalboard` shared across all requests. With stateful `reset=False` processing, concurrent requests would corrupt each other's compressor state. Per-request instances are mandatory.

```python
# Source: Pedalboard v0.9.22 official docs
# https://spotify.github.io/pedalboard/reference/pedalboard.html

from pedalboard import Pedalboard, LowShelfFilter, HighShelfFilter, PeakFilter, Compressor, Clipping
import numpy as np

class HumanismPostFX:
    """Professional vocal post-processing chain for TTS output."""
    
    def __init__(self, config: "PostFXConfig"):
        self._config = config
        self._board = self._build_board(config)
        self._first_call = True
    
    def _build_board(self, cfg: "PostFXConfig") -> Pedalboard:
        """Build pedalboard chain from config intensities."""
        plugins = []
        
        # 1. De-ess (narrow notch at 6.5kHz)
        if cfg.deess_intensity > 0:
            plugins.append(PeakFilter(
                cutoff_frequency_hz=6500,
                gain_db=cfg.deess_intensity * -6.0,  # 0.0=flat, 1.0=-6dB cut
                q=4.0,
            ))
        
        # 2. Low-shelf EQ (warmth at 250Hz)
        if cfg.eq_low_intensity > 0:
            plugins.append(LowShelfFilter(
                cutoff_frequency_hz=250,
                gain_db=cfg.eq_low_intensity * 3.0,  # 0.0=flat, 1.0=+3dB
                q=0.7,
            ))
        
        # 3. High-shelf EQ (air at 8kHz)
        if cfg.eq_high_intensity > 0:
            plugins.append(HighShelfFilter(
                cutoff_frequency_hz=8000,
                gain_db=cfg.eq_high_intensity * 2.0,  # 0.0=flat, 1.0=+2dB
                q=0.7,
            ))
        
        # 4. Compression
        if cfg.compression_intensity > 0:
            plugins.append(Compressor(
                threshold_db=-20.0,
                ratio=1.0 + cfg.compression_intensity * 1.0,  # 0.0=1:1, 1.0=2:1
                attack_ms=10.0,
                release_ms=100.0,
            ))
        
        # 5. Clipping safety (always on)
        plugins.append(Clipping(threshold_db=-0.1))
        
        return Pedalboard(plugins)
    
    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Process a single audio chunk, maintaining state across calls."""
        # Pedalboard processing (de-ess, EQ, compress)
        reset = self._first_call  # Reset on first call only
        self._first_call = False
        processed = self._board.process(audio, sample_rate, reset=reset)
        
        # Saturation (numpy, outside pedalboard)
        if self._config.saturation_intensity > 0:
            processed = self._apply_saturation(processed, self._config.saturation_intensity)
        
        # Final clip (redundant safety after saturation)
        return np.clip(processed, -1.0, 1.0)
    
    def _apply_saturation(self, audio: np.ndarray, intensity: float) -> np.ndarray:
        """Asymmetric soft saturation for even-harmonic warmth."""
        drive = 1.0 + intensity * 2.0   # 1.0=clean, 3.0=moderate drive
        k = intensity * 0.1             # quadratic asymmetry coefficient
        
        positive = np.tanh(drive * audio)
        negative = np.tanh(drive * audio) + k * audio ** 2
        
        return np.where(audio >= 0, positive, negative)
```

### Pattern 2: PostFXConfig Dataclass
**What:** Dataclass with per-effect intensity floats, default all at 1.0 (full chain active).
**When to use:** Always -- configuration for HumanismPostFX.

```python
from dataclasses import dataclass, field

@dataclass
class PostFXConfig:
    """Per-effect intensity controls (0.0 = bypass, 1.0 = full effect)."""
    eq_low_intensity: float = 1.0     # WARM-01: low-shelf at 250Hz
    eq_high_intensity: float = 1.0    # WARM-02: high-shelf at 8kHz
    compression_intensity: float = 1.0 # WARM-03: gentle compression
    deess_intensity: float = 1.0      # WARM-04: sibilance reduction
    saturation_intensity: float = 1.0  # WARM-05: analog warmth
    # WARM-06: limiter always on (safety), no intensity knob
```

### Pattern 3: Integration into TTSInferenceEngine
**What:** Replace class-level `_post_fx` with per-request `HumanismPostFX` instance.
**Key change:** The instance must be created at the start of `inference()` and passed to `get_audio_segment()` or called inline in the streaming loop.

```python
# In TTSInferenceEngine.inference():
post_fx = HumanismPostFX(PostFXConfig())  # per-request instance

# In get_audio_segment() or inline after it:
audio = self.get_audio_segment(result)
audio = post_fx.process(audio, sample_rate)  # stateful, reset=False after first call
```

### Anti-Patterns to Avoid
- **Class-level Pedalboard with reset=False:** Concurrent requests would share compressor state. Always per-request.
- **Calling `board(audio, sr)` instead of `board.process(audio, sr, reset=False)`:** The `__call__` signature defaults `reset=True`, wiping IIR state every chunk. Either use `process()` explicitly or always pass `reset=False` to `__call__`.
- **Using `Limiter` for safety clipping:** Pedalboard's Limiter normalizes audio to [-1, 1] even when input is quiet (GitHub issue #282). Use `Clipping(threshold_db=-0.1)` for transparent peak prevention.
- **Applying saturation inside the Pedalboard chain:** The asymmetric numpy saturation cannot be a Pedalboard plugin. It must be applied between the pedalboard `process()` output and the final `np.clip()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Low-shelf / high-shelf EQ | Manual biquad IIR filter | `pedalboard.LowShelfFilter`, `pedalboard.HighShelfFilter` | IIR coefficient calculation is error-prone; pedalboard wraps JUCE's battle-tested DSP |
| Dynamic range compression | Manual RMS/peak detector + gain reduction | `pedalboard.Compressor` | Attack/release envelope tracking has subtle edge cases (look-ahead, knee shape) |
| Peak limiting / clipping | `np.clip(audio, -1, 1)` before amplification | `pedalboard.Clipping(threshold_db=-0.1)` | Handles dB-scale thresholds correctly, integrates with the chain |
| Streaming state management | Manual IIR filter state save/restore | `board.process(chunk, sr, reset=False)` | Pedalboard tracks all internal plugin state natively |

**Key insight:** Pedalboard handles all the DSP heavy lifting (IIR filter design, compressor envelope, buffer management). The only custom code needed is the asymmetric saturation waveshaper (numpy, ~10 lines) because pedalboard has no built-in asymmetric saturation.

## Common Pitfalls

### Pitfall 1: reset=True Default Destroys Streaming State
**What goes wrong:** Compressor "pumps" at every chunk boundary, EQ has transient artifacts at segment starts.
**Why it happens:** Both `__call__()` and `process()` default to `reset=True`. The current code `self._post_fx(audio, sr)` uses this default.
**How to avoid:** Always pass `reset=False` after the first chunk. Set `reset=True` only on the first call of a new request to clear state from any previous request.
**Warning signs:** A/B test shows chunk-boundary clicks or volume jumps that weren't present before post-FX.

### Pitfall 2: Limiter Normalization
**What goes wrong:** Quiet passages get amplified to full scale, destroying dynamic range. Audio sounds "maxed out" like a brick wall.
**Why it happens:** Pedalboard's `Limiter` contains two internal compressors that normalize before the hard clipper at 0dB (confirmed GitHub issue #282).
**How to avoid:** Use `Clipping(threshold_db=-0.1)` instead of `Limiter()`. This hard-clips only peaks that exceed the threshold, leaving quiet signals untouched.
**Warning signs:** All output audio has identical peak levels regardless of input dynamics.

### Pitfall 3: Shared Instance for Concurrent Requests
**What goes wrong:** Request A's compressor state leaks into Request B's audio. Intermittent, hard to reproduce.
**Why it happens:** If `HumanismPostFX` is a class variable (like the current `_post_fx`), all requests share the same pedalboard instance with `reset=False`.
**How to avoid:** Create a new `HumanismPostFX()` at the start of each `inference()` call. The instance lives only for the duration of that request.
**Warning signs:** Inconsistent audio quality between requests, especially under concurrent load.

### Pitfall 4: Saturation Aliasing at High Drive
**What goes wrong:** Harsh metallic artifacts in high-frequency content after saturation.
**Why it happens:** Nonlinear waveshaping (tanh) generates harmonics above Nyquist that fold back as aliasing. Worse at higher drive levels.
**How to avoid:** Keep drive low (max 3.0 at intensity=1.0) and asymmetry coefficient k small (0.05-0.15). At 44.1kHz sample rate with gentle drive, aliasing is below audible threshold. If artifacts appear during tuning, options: (a) reduce drive, (b) add 2x oversampling with `resampy` (already a dependency).
**Warning signs:** Brightness or harshness that increases with saturation intensity, especially on sibilants.

### Pitfall 5: EQ Boost + Compression Interaction
**What goes wrong:** Low-shelf boost at 250Hz feeds extra energy into the compressor, causing the compressor to react to bass content and "pump" the overall level.
**Why it happens:** Compression comes after EQ in the chain. The compressor's detector sees the boosted low frequencies and triggers gain reduction.
**How to avoid:** Use gentle EQ gains (+3dB max for low-shelf) and moderate compression ratio (2:1 max). If bass pumping occurs, reduce `eq_low_intensity` or raise compressor `threshold_db`. The de-ess-first chain order helps by removing sibilance energy before EQ.
**Warning signs:** Overall volume "breathing" in sync with bass content in the voice.

### Pitfall 6: Post-FX Applied After Crossfade
**What goes wrong:** The crossfade blending in the streaming loop happens on raw audio, then post-FX is applied to the blended result. This means the overlapping region gets double-processed (once in each segment's post-FX, then blended).
**Why it happens:** The current code applies `_post_fx` inside `get_audio_segment()`, which returns processed audio. The crossfader then blends processed segments.
**How to avoid:** This is actually the correct order for stateful processing: apply FX per-segment, then crossfade the results. The alternative (crossfade raw, then FX) would require FX to see the full blended stream, which doesn't match the chunked processing model. Keep the current architecture: `get_audio_segment()` returns raw decoded audio, then apply `post_fx.process()` to each segment before crossfade/yield.

## Code Examples

### Complete Integration Point (TTSInferenceEngine.inference modification)

```python
# Source: Current codebase + pedalboard streaming docs
# https://spotify.github.io/pedalboard/examples.html

# At the top of inference():
from fish_speech.utils.post_fx import HumanismPostFX, PostFXConfig
post_fx = HumanismPostFX(PostFXConfig())

# Replace get_audio_segment call pattern:
# OLD: segment = self.get_audio_segment(result)
# NEW:
raw_segment = self.get_audio_segment_raw(result)  # returns unprocessed numpy
segment = post_fx.process(raw_segment, sample_rate)
```

### Stateful Streaming with reset=False

```python
# Source: Pedalboard v0.9.22 official docs
# https://spotify.github.io/pedalboard/reference/pedalboard.html

board = Pedalboard([LowShelfFilter(cutoff_frequency_hz=250, gain_db=3.0)])

# First chunk: reset=True (or omit, since it's the default)
out1 = board.process(chunk1, 44100, reset=True)

# Subsequent chunks: reset=False to maintain IIR state
out2 = board.process(chunk2, 44100, reset=False)
out3 = board.process(chunk3, 44100, reset=False)
```

### Asymmetric Saturation

```python
# Source: DSP theory - even harmonics from asymmetric waveshaping
# https://www.kvraudio.com/forum/viewtopic.php?t=123354

def asymmetric_saturation(audio: np.ndarray, intensity: float) -> np.ndarray:
    """Even-harmonic analog warmth via asymmetric soft clipping.
    
    Positive half-cycle: tanh(drive * x)          -- symmetric, odd harmonics
    Negative half-cycle: tanh(drive * x) + k*x^2  -- asymmetric, adds even harmonics
    
    The quadratic term on negative half-cycles breaks the odd-symmetry of tanh,
    introducing 2nd and 4th harmonics that mimic tube/transformer coloration.
    """
    if intensity <= 0:
        return audio
    
    drive = 1.0 + intensity * 2.0   # [1.0, 3.0]
    k = intensity * 0.1             # [0.0, 0.1]
    
    driven = drive * audio
    saturated = np.tanh(driven)
    
    # Add quadratic asymmetry only to negative half-cycles
    mask = audio < 0
    saturated[mask] += k * audio[mask] ** 2
    
    return saturated
```

### Clipping as Safety Limiter (instead of Limiter)

```python
# Source: Pedalboard GitHub issue #282
# https://github.com/spotify/pedalboard/issues/282

from pedalboard import Clipping

# Limiter normalizes all audio to [-1, 1] -- unwanted
# Clipping only clips peaks above threshold -- transparent safety
safety = Clipping(threshold_db=-0.1)  # 0.1dB headroom
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `board(chunk, sr)` (reset=True) | `board.process(chunk, sr, reset=False)` | Always (pedalboard design) | Stateful streaming requires explicit `reset=False` |
| `Limiter()` for peak safety | `Clipping(threshold_db=-0.1)` | Recognized via issue #282 (2024) | Limiter normalizes; Clipping is transparent |
| Symmetric `tanh(x)` saturation | Asymmetric `tanh(x) + k*x^2` on negative | DSP theory | Even harmonics for analog warmth vs. only odd harmonics |

**Deprecated/outdated:**
- pedalboard 0.9.18 was **yanked** due to a segfault in MP3 handling. Use 0.9.22 (current).
- The project's existing `PeakFilter(3500Hz, +1.5dB)` will be replaced by the new chain per CONTEXT.md decision.

## Open Questions

1. **Compressor state continuity verification**
   - What we know: Pedalboard docs say `reset=False` maintains state. Multiple sources confirm this.
   - What's unclear: Whether JUCE's compressor implementation specifically maintains attack/release envelope state correctly across very short chunks (sub-second segments are common in streaming).
   - Recommendation: First task should include an empirical test -- process a known signal in one shot vs. chunked with `reset=False`, compare waveforms. This was flagged as a concern in STATE.md.

2. **Saturation drive parameter range**
   - What we know: k in [0.05, 0.15] is recommended in CONTEXT.md. Drive of 3.0 at max intensity.
   - What's unclear: Whether these produce audible aliasing at 44.1kHz with real TTS audio (not just test tones).
   - Recommendation: Tune by ear during A/B testing. If artifacts appear, reduce drive or add 2x oversampling via `resampy` (already installed).

3. **Post-FX position relative to crossfade**
   - What we know: Current `_post_fx` is applied inside `get_audio_segment()` (line 279), before crossfade.
   - What's unclear: With stateful compressor, should FX be applied before or after the crossfade blending?
   - Recommendation: Apply FX per-segment before crossfade. This matches the stateful model (compressor sees a continuous stream of segments). Move FX application out of `get_audio_segment()` into the streaming loop, after decoding but before crossfade/yield.

## Project Constraints (from CLAUDE.md)

- **No local models:** GPU dedicated to training, never start LLM servers
- **Working directory:** Always use project-seishin/fish-speech
- **Push to project-seishin main:** Commit fish-speech changes via parent repo
- **Performance constraints:** VRAM ~9.9GB, TTFA ~250ms, RTF ~0.33x baseline; small increases OK
- **No co-author tags** in git commits
- **No temporal file names:** Never create fix-v2.md, new-approach.md, etc.
- **Clear context before coding:** Research/plan first, save context, /clear, then code

## Sources

### Primary (HIGH confidence)
- [Pedalboard v0.9.22 API Reference](https://spotify.github.io/pedalboard/reference/pedalboard.html) -- `process()` signature, `reset` parameter, all plugin classes
- [Pedalboard v0.9.22 Examples](https://spotify.github.io/pedalboard/examples.html) -- chunked streaming with `reset=False`
- [Pedalboard GitHub: Compressor.h source](https://github.com/spotify/pedalboard/blob/master/pedalboard/plugins/Compressor.h) -- default params: threshold_db=0, ratio=1, attack_ms=1.0, release_ms=100
- [Pedalboard GitHub issue #282: Limiter normalization](https://github.com/spotify/pedalboard/issues/282) -- confirmed Limiter normalizes to [-1, 1]
- [Pedalboard GitHub issue #279: TTS audio enhancement](https://github.com/spotify/pedalboard/issues/279) -- community TTS FX chain example
- Fish Speech codebase: `fish_speech/inference_engine/__init__.py` -- current `_post_fx` usage, streaming architecture

### Secondary (MEDIUM confidence)
- [KVR Audio: Even and odd harmonic distortion](https://www.kvraudio.com/forum/viewtopic.php?t=123354) -- asymmetric waveshaping theory for even harmonics
- [Elementary Audio: Distortion and Waveshaping](https://www.elementary.audio/docs/tutorials/distortion-saturation-wave-shaping) -- asymmetric saturation implementation patterns
- [Oversampling for Nonlinear Waveshaping (AES paper)](https://www.researchgate.net/publication/333688079_Oversampling_for_Nonlinear_Waveshaping_Choosing_the_Right_Filters) -- aliasing reduction for waveshaping

### Tertiary (LOW confidence)
- Pedalboard `Limiter` default params (threshold_db=-10.0, release_ms=100.0) -- from training data, not verified against source. LOW confidence but irrelevant since we're using `Clipping` instead.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pedalboard already installed and used in codebase, all plugins verified available
- Architecture: HIGH -- `process(reset=False)` streaming pattern officially documented, per-request scoping straightforward
- Pitfalls: HIGH -- Limiter normalization confirmed via GitHub issue, reset default confirmed via official docs
- Saturation: MEDIUM -- asymmetric waveshaping theory is well-established, but tuning parameters (drive, k) need empirical validation
- Aliasing: MEDIUM -- at gentle drive levels (max 3.0) and 44.1kHz, aliasing should be inaudible, but not empirically verified for this specific TTS use case

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (pedalboard stable, no breaking changes expected)
