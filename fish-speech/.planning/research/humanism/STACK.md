# Technology Stack: TTS Humanism & Naturalness

**Project:** Fish Speech S2-Pro TTS Humanism (v2.0)
**Researched:** 2026-04-13
**Overall confidence:** HIGH (pedalboard verified in codebase; DSP techniques verified against multiple sources)

## Executive Summary

The existing Fish Speech inference engine already uses `pedalboard` (Spotify, v0.9.22) with a single `PeakFilter` at 3500Hz. The humanism milestone expands this post-FX chain significantly but requires **only one new dependency** (`pyworld` for F0 analysis). Everything else is achievable with pedalboard (already installed), numpy (already installed), and a handful of WAV impulse response files (static assets, not code dependencies).

The stack strategy is: maximize pedalboard (JUCE-backed, C++ speed, production-tested at Spotify), use numpy for custom DSP where pedalboard lacks a built-in (soft saturation, asymmetric clipping), and use pyworld only for prosody analysis (not in the real-time path). No heavyweight NLP or ML libraries needed.

## Existing Stack (Already in Codebase -- Do NOT Replace)

| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| pedalboard | >=0.9.0 (0.9.22 latest) | Post-FX chain (PeakFilter) | In `pyproject.toml`, used in `inference_engine/__init__.py` |
| numpy | 2.4.4 | Audio array ops, crossfade | Core dependency, used everywhere |
| soundfile | 0.13.1 | WAV I/O | Used in views.py |
| torch / torchaudio | 2.8.0+cu128 | Model inference, potential pitch_shift | Core dependency |
| Python stdlib (wave, io) | 3.11 | WAV headers, BytesIO | Used in utils.py |

## Recommended Stack Additions

### 1. Post-Processing Chain (Warmth/Presence) -- Pedalboard

**Library:** `pedalboard` (already installed)
**Version:** 0.9.22 (released Feb 2, 2026)
**Confidence:** HIGH -- verified in codebase, API confirmed via official docs

Expand the existing `_post_fx` Pedalboard chain from a single PeakFilter to a full vocal processing chain. Pedalboard provides all the building blocks natively:

| Effect | Pedalboard Class | Purpose | Parameters |
|--------|-----------------|---------|------------|
| Low-shelf warmth | `LowShelfFilter` | Boost low-mids for body/warmth | `cutoff_frequency_hz=250, gain_db=2.0, q=0.7` |
| Presence boost | `PeakFilter` | (existing) Clarity in vocal range | `cutoff_frequency_hz=3500, gain_db=1.5, q=0.7` |
| High-shelf air | `HighShelfFilter` | Subtle top-end shimmer/breath detail | `cutoff_frequency_hz=8000, gain_db=1.0, q=0.7` |
| Gentle compression | `Compressor` | Even out dynamics, add "glue" | `threshold_db=-20, ratio=2.0, attack_ms=10, release_ms=100` |
| Room tone / presence | `Convolution` | Convolve with short room IR for "not a vacuum" feel | `impulse_response_filename="ir_small_room.wav", mix=0.05` |
| Peak limiting | `Limiter` | Prevent clipping after boosts | `threshold_db=-1.0, release_ms=100` |

**Recommended chain order** (based on professional vocal chain practice):

```python
from pedalboard import (
    Pedalboard, LowShelfFilter, PeakFilter, HighShelfFilter,
    Compressor, Convolution, Limiter, Gain
)

_post_fx = Pedalboard([
    # 1. Subtractive EQ -- remove mud
    # (handled by existing Fish Speech DAC output which is already clean)

    # 2. Gentle compression -- even out dynamics before EQ
    Compressor(threshold_db=-20, ratio=2.0, attack_ms=10, release_ms=100),

    # 3. Tonal shaping
    LowShelfFilter(cutoff_frequency_hz=250, gain_db=2.0, q=0.7),    # Warmth
    PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7),       # Presence (existing)
    HighShelfFilter(cutoff_frequency_hz=8000, gain_db=1.0, q=0.7),   # Air

    # 4. Subtle room tone (very low mix)
    Convolution("assets/ir/small_room_close.wav", mix=0.03),

    # 5. Safety limiter
    Limiter(threshold_db=-1.0, release_ms=100),
])
```

**Why pedalboard over scipy/numpy for EQ/compression:**
- JUCE-backed C++ -- processes audio 300x faster than pySoX
- Already a dependency (zero additional install cost)
- Professional-grade algorithms (same code that powers Spotify's AI DJ)
- `Pedalboard` objects are callable: `audio_out = _post_fx(audio_in, sample_rate)`
- Supports chaining with automatic buffer management

**Why NOT build custom EQ/compression in numpy:**
- Reimplementing biquad filters, compressor envelopes, and convolution reverb in numpy is hundreds of lines for worse quality
- scipy.signal shelving filters require manual RBJ cookbook coefficient calculation
- No anti-aliasing, no proper lookahead limiting

### 2. Soft Saturation (Analog Warmth) -- NumPy

**Library:** numpy (already installed)
**Confidence:** HIGH -- standard DSP technique, well-documented

Pedalboard's `Distortion` is too aggressive for speech. Instead, use a custom asymmetric soft clipper in numpy to generate even harmonics (warmth) without odd-harmonic grit.

```python
import numpy as np

def warm_saturate(audio: np.ndarray, drive: float = 0.3, asymmetry: float = 0.15) -> np.ndarray:
    """Asymmetric soft saturation for even-harmonic warmth.

    - drive: 0.0 = bypass, 0.3 = subtle tape warmth, 1.0 = heavy saturation
    - asymmetry: breaks symmetry to generate 2nd harmonic (even = warm)
      0.0 = symmetric (odd harmonics only), 0.15 = gentle tube-like warmth
    """
    x = audio * (1.0 + drive * 3.0)  # Pre-gain
    x = x + asymmetry * x**2          # Add asymmetry for even harmonics
    x = np.tanh(x)                     # Soft clip
    return x * (1.0 / (1.0 + drive))  # Compensate output level
```

**Why asymmetric tanh over symmetric tanh:**
- Symmetric tanh generates only odd harmonics (3rd, 5th, 7th) -- sounds gritty/aggressive
- Adding a quadratic term (`asymmetry * x^2`) before tanh produces even harmonics (2nd, 4th) -- the "warmth" that tube amps and tape machines are known for
- This is the standard technique in analog modelling (confirmed by CCRMA Stanford, musicdsp.org, KVR Audio DSP forums)

**Why NOT pedalboard.Distortion:**
- `Distortion` is designed for guitar -- too aggressive even at low drive
- No asymmetry control -- only odd harmonics
- Clipping characteristic is hard, not tape-like

### 3. Prosody Analysis -- PyWorld (NEW DEPENDENCY)

**Library:** `pyworld`
**Version:** 0.3.5 (released Jan 20, 2025)
**Confidence:** HIGH -- standard tool in TTS/voice conversion research, MIT-like license (no patent restrictions)
**Install:** `pip install pyworld`

PyWorld extracts F0 (pitch), spectral envelope, and aperiodicity from speech. Use it to **analyze** generated TTS output and detect monotonic or unnatural prosody patterns. NOT for real-time modification (too slow), but for:

1. **Measuring pitch variation** -- detect if output is too monotone (low F0 standard deviation)
2. **Detecting missing pauses** -- F0 = 0 indicates silence/unvoiced; check if pauses exist at expected boundaries
3. **Validating prosody improvements** -- before/after comparison metric

```python
import pyworld as pw

f0, sp, ap = pw.wav2world(audio.astype(np.float64), sample_rate)
# f0: pitch contour (Hz). 0 = unvoiced/silence
# Measure naturalness: std(f0[f0 > 0]) should be 20-60 Hz for natural speech
```

**Why pyworld over parselmouth (Praat):**
- Parselmouth is GPL v3 -- license contamination risk for the project
- PyWorld is BSD-like (no patent restrictions) -- safe for any use
- PyWorld is lighter (C library + thin wrapper vs full Praat embedded)
- For analysis-only use (not resynthesis), PyWorld's DIO+StoneMask F0 extraction is sufficient

**Why NOT parselmouth:**
- GPL v3 license (parselmouth wraps Praat which is GPL)
- Heavier dependency (full Praat C/C++ codebase)
- Formant analysis capabilities are overkill for this use case

**Why NOT torchaudio.functional.pitch_shift:**
- That's for pitch *modification*, not analysis
- We need F0 *measurement*, not F0 *shifting*
- torchaudio pitch_shift uses STFT phase vocoder -- introduces artifacts not suitable for production TTS

### 4. Dynamic Pause/Silence Injection -- NumPy + Text Processing

**Library:** numpy (already installed), Python stdlib `re`
**Confidence:** HIGH -- straightforward audio/text manipulation

Two-level pause injection:

**Level 1: Text-level (pre-generation)**
Insert punctuation markers before sending text to Fish Speech. The model already responds to punctuation with natural pauses:

| Punctuation | Typical Pause | When to Inject |
|-------------|--------------|----------------|
| `,` (comma) | ~200-300ms | Clause boundaries, after subordinate clauses |
| `;` (semicolon) | ~300-400ms | Between independent clauses |
| `.` (period) | ~400-600ms | Sentence boundaries |
| `...` (ellipsis) | ~500-800ms | Trailing off, hesitation |
| `--` (em dash) | ~200-400ms | Parenthetical, interruption feel |

**Level 2: Audio-level (post-generation)**
Insert calibrated silence segments at detected pause points:

```python
def insert_silence(audio: np.ndarray, position: int,
                   duration_ms: float, sr: int = 44100) -> np.ndarray:
    """Insert silence at a sample position with smooth fade in/out."""
    n_samples = int(sr * duration_ms / 1000)
    silence = np.zeros(n_samples, dtype=audio.dtype)

    # 5ms fade to avoid clicks
    fade_len = int(sr * 0.005)
    if fade_len > 0 and position > fade_len:
        fade_out = np.linspace(1.0, 0.0, fade_len)
        audio[position - fade_len:position] *= fade_out

    return np.concatenate([audio[:position], silence, audio[position:]])
```

**Why text-level is preferred over audio-level:**
- Fish Speech's DualAR transformer already models prosody from punctuation
- Injecting punctuation lets the model generate natural pauses with proper pitch contour
- Audio-level silence insertion is a fallback for fine-tuning specific pause durations

### 5. Room Tone / Impulse Responses -- Static WAV Assets

**Library:** pedalboard `Convolution` (already installed)
**Confidence:** HIGH

The `Convolution` effect in pedalboard accepts WAV files as impulse responses. Ship a small set of room IR files as static assets:

| IR File | Source | Character | Mix Level |
|---------|--------|-----------|-----------|
| `small_room_close.wav` | Airborne Sound (free, royalty-free) or Voxengo (free) | Tight, intimate room. Close mic perspective. | 0.02-0.05 |
| `medium_room.wav` | Voxengo free IR pack | Slightly larger space for "podcast" feel | 0.03-0.06 |

**Selection criteria for room IRs:**
- Short RT60 (< 0.3s) -- we want "room presence", not "reverb"
- Close-mic perspective -- matches the "someone speaking to you" feel
- Dry character -- subtle coloration, not audible reverb tail
- 44.1kHz sample rate to match DAC output (avoids resampling)

**Free IR sources (royalty-free, confirmed):**
- [Voxengo Free Reverb IRs](https://www.voxengo.com/impulses/) -- 44.1kHz 16-bit WAV, royalty-free
- [Airborne Sound Household IRs](https://www.airbornesound.com/2024/07/10/introducing-a-free-impulse-response-library-raw-irs-household/) -- 96kHz 24-bit, close/medium/far perspectives, royalty-free
- [OpenSLR RIR Database](https://www.openslr.org/28/) -- research-grade, simulated and real

**Why NOT pyroomacoustics for synthesized IRs:**
- Overkill -- we need 1-2 static WAV files, not a room simulation engine
- Additional dependency with Cython compilation requirements
- Real recorded IRs sound more natural than ISM-simulated ones for this purpose

### 6. Breathing Sound Evaluation -- Decision: SKIP Implementation

**Confidence:** HIGH (well-reasoned skip)

After research, breathing sound insertion is explicitly **not recommended** for this milestone:

**Why skip:**
1. Fish Speech S2-Pro already generates natural breathing from reference audio -- the DualAR transformer learns breath patterns from the training data and reference clip
2. Injecting synthetic breath sounds post-hoc sounds worse than model-generated ones
3. No Python library produces convincing breath synthesis -- Amazon Polly's `<amazon:breath>` tag is the only decent implementation, and it requires their proprietary engine
4. Glottal pulse modeling (LF model + LPC) can synthesize breath-like sounds but requires significant DSP engineering for dubious quality improvement
5. The reference audio (17.27s clip) already contains natural breathing patterns that the model replicates

**What to do instead:**
- Ensure the reference audio includes natural breathing (it does -- 17.27s clip)
- Verify that text-level pause injection gives the model space to insert breaths where natural
- If specific breathing is needed later, train with breath-annotated data (LoRA milestone)

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Post-FX engine | pedalboard | scipy.signal + manual biquads | Already installed, 300x faster, production-grade |
| Saturation | numpy asymmetric tanh | pedalboard.Distortion | Distortion too aggressive for speech, no asymmetry control |
| F0 analysis | pyworld | parselmouth (Praat) | GPL v3 license risk, heavier dependency |
| F0 analysis | pyworld | librosa.pyin | librosa is heavy, pyin is slower, pyworld is the TTS standard |
| Room presence | pedalboard.Convolution + static IRs | pyroomacoustics | Overkill, compilation deps, synthetic IRs less natural |
| Room presence | pedalboard.Convolution | pedalboard.Reverb | Reverb is algorithmic (metallic). Convolution with real IRs sounds organic. |
| Pause injection | Text-level punctuation + numpy silence | SSML parser | Fish Speech doesn't support SSML. Punctuation is its native pause mechanism. |
| Breathing | Skip (model handles it) | Synthetic breath injection | No convincing Python implementation exists |
| Prosody modification | Text-level emotion tags | torchaudio.pitch_shift | Phase vocoder artifacts; emotion tags are the native mechanism |
| Compression | pedalboard.Compressor | numpy envelope follower | Hundreds of lines for worse quality |

## Complete Dependency Changes

### New Dependencies (1 total)

```bash
pip install pyworld  # v0.3.5 -- F0 analysis for prosody measurement
```

### New Static Assets

```
assets/ir/small_room_close.wav   # From Voxengo or Airborne Sound (royalty-free)
assets/ir/medium_room.wav        # Optional, for alternate "space" feel
```

### Existing Dependencies (No Changes)

```
pedalboard>=0.9.0    # Already in pyproject.toml
numpy                # Already installed
soundfile            # Already installed
torch / torchaudio   # Already installed
```

## Architecture: Where Each Tool Fits

```
Text Input
    |
    v
[Text Preprocessor] ---- punctuation injection, pause markers (stdlib re)
    |
    v
[Fish Speech DualAR] --- generates semantic tokens with natural prosody
    |
    v
[DAC Decoder] ---------- VQ tokens to audio waveform
    |
    v
[Warm Saturate] -------- numpy asymmetric tanh (subtle, drive=0.2-0.3)
    |
    v
[Post-FX Chain] -------- pedalboard Pedalboard([
    |                        Compressor,
    |                        LowShelfFilter,   # warmth
    |                        PeakFilter,        # presence (existing)
    |                        HighShelfFilter,   # air
    |                        Convolution,       # room tone
    |                        Limiter            # safety
    |                    ])
    |
    v
[Audio Output] --------- StreamingCrossfader -> HTTP chunked response
```

**PyWorld sits outside the real-time path:**
```
[Generated Audio] ---> pyworld.wav2world() ---> F0 stats, pause detection
                                                 |
                                                 v
                                          [Quality metrics / tuning feedback]
```

## Sources

### Verified (HIGH confidence)
- Fish Speech codebase: `fish_speech/inference_engine/__init__.py` -- pedalboard already imported and used
- [Pedalboard v0.9.22 Documentation](https://spotify.github.io/pedalboard/) -- full effects list, API reference
- [Pedalboard GitHub](https://github.com/spotify/pedalboard) -- release history, Python 3.10-3.14 support
- [PyWorld v0.3.5 on PyPI](https://pypi.org/project/pyworld/) -- F0/SP/AP extraction, BSD-like license
- [Stanford CCRMA: Soft Clipping](https://ccrma.stanford.edu/~jos/pasp/Soft_Clipping.html) -- tanh waveshaping theory
- [Voxengo Free IRs](https://www.voxengo.com/impulses/) -- royalty-free 44.1kHz WAV impulse responses
- [SciPy v1.17.0 signal docs](https://docs.scipy.org/doc/scipy/reference/signal.html) -- IIR filter reference (for comparison)

### Production references (MEDIUM confidence)
- [Icon Collective: Effects Chain Order](https://www.mixinglessons.com/shelving-filter/) -- professional vocal chain ordering
- [Sage Audio: Vocal Effect Chaining](https://www.sageaudio.com/articles/how-to-chain-vocal-effects) -- saturation before compression, EQ after
- [musicdsp.org: Variable Hardness Clipping](https://www.musicdsp.org/en/latest/Effects/104-variable-hardness-clipping-function.html) -- tanh variants
- [KVR Audio: Variable tanh saturation](https://www.kvraudio.com/forum/viewtopic.php?t=465091) -- asymmetry for even harmonics
- [audiomentations TanhDistortion](https://iver56.github.io/audiomentations/waveform_transforms/tanh_distortion/) -- reference implementation

### Research references (MEDIUM confidence)
- [Duration-aware pause insertion (arXiv 2302.13652)](https://arxiv.org/abs/2302.13652) -- pre-trained LM for pause prediction
- [Prosodic Parameter Manipulation in TTS (arXiv 2409.12176)](https://arxiv.org/abs/2409.12176) -- F0/duration/energy adjustment
- [Stochastic Prosody Modeling (arXiv 2507.00227)](https://arxiv.org/html/2507.00227v1) -- normalizing flows for natural prosody
- [DeepFry: Vocal Fry Detection](https://arxiv.org/abs/2203.17019) -- creaky voice detection (reference only)
- [bagrounds.org: Semicolon Injection for TTS Pauses](https://bagrounds.org/ai-blog/2026-03-10-tts-semicolon-injection) -- practical punctuation-based pause insertion
