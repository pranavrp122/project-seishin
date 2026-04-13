# Phase 2: Post-FX Chain — Context

## Phase Goal
Every utterance sounds warmer, more present, and more polished through a professional audio processing chain, with zero changes to text or generation pipeline.

## Requirements
- **WARM-01**: Low-shelf EQ at 250Hz adds body/warmth
- **WARM-02**: High-shelf at 8kHz adds subtle air/shimmer
- **WARM-03**: Gentle compression (2:1, -20dB threshold) evens dynamics without pumping
- **WARM-04**: De-essing reduces sibilance (narrow cut at 6.5kHz)
- **WARM-05**: Asymmetric soft saturation adds even-harmonic analog warmth (tanh + quadratic)
- **WARM-06**: Safety limiter prevents clipping after boosts
- **WARM-07**: Post-FX chain maintains streaming compatibility (no audible state-reset artifacts)
- **WARM-08**: Each effect has intensity parameter (0.0-1.0) for A/B tuning

## Existing Code Patterns

### Current Post-FX
`TTSInferenceEngine._post_fx` in `fish_speech/inference_engine/__init__.py` (line 25-27):
```python
_post_fx = Pedalboard([
    PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7),
])
```
Applied per-segment in `get_audio_segment()` (line 279): `return self._post_fx(audio, sr)`

### Audio Pipeline
- Sample rate: 44100 Hz, mono
- Output format: 16-bit PCM WAV (streaming), wav/mp3/flac/opus (non-streaming)
- Streaming: yields `InferenceResult` with codes `header`, `segment`, `final`
- Sub-chunk crossfade blending already exists (1764 sample overlap)
- `pedalboard>=0.9.0` already in pyproject.toml dependencies

### Baseline Metrics (from Phase 1)
- Mean F0: 236.4 Hz, CV: 0.155 (moderate, 0 expressive clips)
- Mean pauses/clip: 4.0, mean pause duration: 274ms
- Reusable analysis scripts: `analyze_f0.py`, `analyze_pauses.py` with `--input-dir`

## Gray Areas — Resolved

### 1. Effect Chain Order
**Decision**: De-ess → EQ → Compress → Saturate → Limiter
**Rationale**: Industry-standard vocal chain. De-ess first so EQ boosts don't amplify sibilance. Compression after EQ so compressor sees shaped signal. Saturation after compression for warm harmonic addition on controlled dynamics. Limiter last as safety net.

### 2. Streaming State Persistence (WARM-07)
**Decision**: Use pedalboard's stateful `process()` method, keeping the Pedalboard instance alive per inference request
**Rationale**: The default `__call__()` resets IIR filter state between invocations, which would cause compressor attack/release and EQ filter state to reset at every chunk boundary. The `process()` method maintains internal state across calls. TTSInferenceEngine already scopes per-request, providing a natural lifetime boundary for the stateful pedalboard instance.
**Risk**: Needs empirical validation — this was flagged as a concern in STATE.md.

### 3. Code Architecture
**Decision**: Create `HumanismPostFX` class in `fish_speech/utils/post_fx.py`, replace `_post_fx` usage in TTSInferenceEngine
**Rationale**: Keeps inference engine clean. FX chain becomes independently testable. Configuration via dataclass allows serialization and API exposure. The existing `_post_fx` PeakFilter at 3500Hz will be incorporated into the new chain (or superseded by the new EQ bands).

### 4. Intensity Parameter Architecture (WARM-08)
**Decision**: Dataclass with per-effect 0.0-1.0 floats. Interpolation strategy per effect type:
- **EQ (WARM-01, WARM-02)**: `gain_db = intensity * target_gain_db` (0.0 = flat, 1.0 = full boost)
- **Compression (WARM-03)**: `ratio = 1.0 + intensity * (target_ratio - 1.0)`, threshold interpolated (0.0 = no compression, 1.0 = full)
- **De-ess (WARM-04)**: `gain_db = intensity * target_cut_db` (0.0 = no cut, 1.0 = full cut)
- **Saturation (WARM-05)**: `drive = intensity * max_drive` (0.0 = clean, 1.0 = full saturation)
- **Limiter (WARM-06)**: Always on at 1.0 intensity (safety; only threshold adjustable)
**Rationale**: Linear interpolation is predictable and debuggable. Each effect can be fully bypassed at 0.0.

### 5. De-essing Implementation (WARM-04)
**Decision**: Static parametric notch filter at 6.5kHz using pedalboard's PeakFilter with negative gain
**Rationale**: WARM-04 specifies "narrow cut at 6.5kHz". A static notch is simpler, predictable, and uses existing pedalboard primitives. Dynamic sidechain de-essing is better for speech with varying sibilance but adds complexity beyond what's needed for v1.

### 6. Saturation Implementation (WARM-05)
**Decision**: Custom numpy implementation — `tanh(x)` for positive, `tanh(x) + k*x²` for negative, applied outside pedalboard chain
**Rationale**: Pedalboard lacks asymmetric saturation. Even-harmonic generation requires asymmetric waveshaping (positive and negative half-cycles processed differently). Apply after pedalboard chain but before limiter, or implement as a separate step.
**Note**: The quadratic asymmetry coefficient `k` should be small (0.05-0.15 range) to avoid harsh distortion.

### 7. A/B Testing Approach
**Decision**: Re-generate Phase 1 corpus prompts with FX enabled, run existing analysis scripts, plus manual listening
**Rationale**: Phase 1 established baseline metrics and reusable scripts. Re-running the same 24 prompts with post-FX gives direct A/B comparison. F0 should be unchanged (post-FX doesn't alter pitch), but pause detection may be affected by compression/limiting changing RMS levels.

### 8. Existing PeakFilter Disposition
**Decision**: Replace the existing `PeakFilter(3500Hz, +1.5dB, Q=0.7)` with the new chain
**Rationale**: The new chain's EQ bands (250Hz shelf, 8kHz shelf) plus de-ess (6.5kHz notch) provide more comprehensive frequency shaping. The old 3.5kHz presence boost can be optionally added as a mid-range presence band if A/B testing shows it's needed, but it's not in the requirements.

## Dependencies
- **Phase 1 outputs**: Baseline corpus WAVs at `/home/prana/tts-test/outputs/baseline_corpus/`, analysis JSONs, analysis scripts
- **Libraries**: pedalboard (already installed), numpy (already installed)
- **No new dependencies required**

## Risks
1. **Compressor state across chunks**: If pedalboard's `process()` doesn't maintain state as expected, streaming audio may have audible pumping at boundaries. Mitigation: test empirically early.
2. **Saturation artifacts**: Custom numpy saturation may introduce aliasing at high frequencies. Mitigation: apply gentle oversampling or keep drive low.
3. **EQ + compression interaction**: Boosting 250Hz then compressing may cause muddy low-end pumping. Mitigation: use sidechain-aware compression or reduce low-shelf gain.

---
*Context gathered: 2026-04-13 (auto-resolved, --auto mode)*
