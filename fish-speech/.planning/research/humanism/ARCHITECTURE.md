# Architecture Patterns: TTS Humanism & Naturalness

**Domain:** Speech post-processing and naturalness enhancement
**Researched:** 2026-04-13

## Recommended Architecture

The humanism system operates at two layers: **pre-generation** (text manipulation) and **post-generation** (audio processing). These are separate concerns with no coupling between them.

```
                    PRE-GENERATION                          POST-GENERATION
                    
Text Input -----> [PauseInjector] -----> Fish Speech -----> [WarmSaturate] -----> [PostFXChain] -----> Output
                       |                  DualAR +              |                      |
                       |                  DAC Decoder           |                      |
                       v                                        v                      v
                  Punctuation rules                     numpy asymmetric         pedalboard
                  (regex, lookup table)                 tanh (5 lines)           Pedalboard([...])
```

### Component Boundaries

| Component | Responsibility | Input | Output | Communicates With |
|-----------|---------------|-------|--------|-------------------|
| **PauseInjector** | Insert punctuation at clause boundaries for natural pauses | Raw text string | Modified text string with added punctuation | Fish Speech text encoder (upstream) |
| **WarmSaturate** | Add even-harmonic warmth via asymmetric soft clipping | numpy float32 audio array | numpy float32 audio array (same shape) | PostFXChain (downstream) |
| **PostFXChain** | Compression, EQ, room convolution, limiting | numpy float32 audio array | numpy float32 audio array (same shape) | StreamingCrossfader (downstream) |
| **ProsodyAnalyzer** | Measure F0 variation, pause timing, quality metrics | numpy float64 audio array | Dict of metrics (f0_std, pause_count, etc.) | None (diagnostic, offline) |

### Data Flow

```
1. Text arrives via ServeTTSRequest
2. PauseInjector.process(text) -> text with injected punctuation
3. Text enters existing Fish Speech pipeline (DualAR -> VQ tokens -> DAC decode)
4. Raw audio (numpy float32, 44.1kHz mono) exits DAC decoder
5. WarmSaturate.process(audio) -> audio with subtle harmonic richness
6. PostFXChain.process(audio, sample_rate) -> audio with warmth/presence/dynamics
7. StreamingCrossfader handles chunk boundaries (existing)
8. Audio goes to HTTP streaming response (existing)

Parallel/offline:
9. ProsodyAnalyzer.analyze(audio) -> metrics dict (for tuning, not production path)
```

## Patterns to Follow

### Pattern 1: Effect Chain as Configuration

**What:** Define the entire post-FX chain as a declarative configuration, not procedural code.

**When:** Always. The chain will be tuned frequently during development.

**Why:** Pedalboard objects are mutable lists. Effects can be appended, removed, or parameter-tweaked without touching the processing code. This separates "what effects to apply" from "how to apply effects."

**Example:**
```python
from pedalboard import (
    Pedalboard, Compressor, LowShelfFilter, PeakFilter,
    HighShelfFilter, Convolution, Limiter
)

# Configuration -- easy to tune, A/B test, or disable individual effects
_post_fx = Pedalboard([
    Compressor(threshold_db=-20, ratio=2.0, attack_ms=10, release_ms=100),
    LowShelfFilter(cutoff_frequency_hz=250, gain_db=2.0, q=0.7),
    PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7),
    HighShelfFilter(cutoff_frequency_hz=8000, gain_db=1.0, q=0.7),
    Convolution("assets/ir/small_room_close.wav", mix=0.03),
    Limiter(threshold_db=-1.0, release_ms=100),
])

# Processing is a single call
audio_out = _post_fx(audio_in, sample_rate)
```

### Pattern 2: Text Preprocessor as Pure Function

**What:** PauseInjector is a pure function: text in, text out. No state, no side effects.

**When:** Before sending text to the model.

**Why:** Pure functions are testable, composable, and have zero risk of breaking the existing pipeline. The function can be unit-tested with string assertions, no audio generation needed.

**Example:**
```python
import re

def inject_pauses(text: str) -> str:
    """Insert punctuation at natural pause points.

    Rules (applied in order):
    1. Add comma after subordinating conjunctions if missing
    2. Add comma before coordinating conjunctions in compound sentences
    3. Ensure sentence-ending punctuation exists
    4. Convert bare line breaks to sentence boundaries
    """
    # Example: "because the rain was heavy we stayed inside"
    # becomes: "because the rain was heavy, we stayed inside"
    subordinating = r'\b(because|although|while|when|if|since|after|before|unless|until)\b'
    text = re.sub(
        rf'({subordinating}\s+[^,;.!?]+?)(\s+(?:we|they|he|she|it|I|you)\b)',
        r'\1,\2',
        text
    )
    return text
```

### Pattern 3: Saturation Before Chain

**What:** Apply numpy saturation before the pedalboard chain, not inside it.

**When:** Always. Saturation generates new harmonics that the downstream EQ and compressor then shape.

**Why:** Pedalboard doesn't support custom numpy-based effects as chain elements. Keep the numpy saturation as a separate step that feeds into the pedalboard chain. This also allows independently bypassing saturation.

**Example:**
```python
def apply_humanism(audio: np.ndarray, sr: int) -> np.ndarray:
    """Full humanism processing pipeline."""
    # Step 1: Saturation (numpy, before chain)
    audio = warm_saturate(audio, drive=0.25, asymmetry=0.12)

    # Step 2: Post-FX chain (pedalboard)
    audio = _post_fx(audio, sr)

    return audio
```

### Pattern 4: Bypass Architecture for A/B Testing

**What:** Every effect should be individually bypassable via a simple flag.

**When:** During development and tuning.

**Why:** The only way to validate each effect's contribution is to A/B test with and without it. "Does the compressor help or hurt?" requires hearing it both ways.

**Example:**
```python
class HumanismConfig:
    saturation_enabled: bool = True
    saturation_drive: float = 0.25
    saturation_asymmetry: float = 0.12
    compressor_enabled: bool = True
    low_shelf_enabled: bool = True
    low_shelf_gain_db: float = 2.0
    presence_enabled: bool = True      # Existing PeakFilter
    air_enabled: bool = True
    room_tone_enabled: bool = True
    room_tone_mix: float = 0.03
    limiter_enabled: bool = True
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Processing in the Token Loop

**What:** Applying audio effects inside the per-token or per-segment generation loop.

**Why bad:** Post-FX should run once on the final audio of each chunk, not on every intermediate decode step. Running effects on partial audio creates discontinuities and wastes compute.

**Instead:** Apply all humanism processing after the DAC decoder produces a complete chunk, before the StreamingCrossfader.

### Anti-Pattern 2: Stateful Effects Across Chunks Without Reset

**What:** Using pedalboard Compressor across streaming chunks without understanding its state behavior.

**Why bad:** Compressor maintains internal gain-reduction state. If chunk N ends with a loud passage and chunk N+1 starts quiet, the compressor's gain reduction may carry over inappropriately. However, pedalboard's `process()` method IS designed to be called repeatedly on consecutive chunks (it's used for streaming at Spotify).

**Instead:** Instantiate `_post_fx` once, call `_post_fx(chunk, sr)` per chunk. Pedalboard maintains correct internal state. Do NOT recreate the Pedalboard object per chunk. Do NOT try to manually reset state.

### Anti-Pattern 3: Over-Processing

**What:** Stacking too many effects or using aggressive parameters.

**Why bad:** Each effect introduces subtle artifacts. Compression + saturation + heavy EQ + reverb = "radio DJ voice" not "natural human." The goal is that listeners should NOT notice any processing -- they should just feel the speech sounds "good."

**Instead:** Start with all effects at minimum intensity. Increase one parameter at a time. If you can hear the effect distinctly, it's probably too much. Target: "Can't tell it's processed, but it sounds better."

### Anti-Pattern 4: Post-hoc Pitch/Time Modification

**What:** Using torchaudio.pitch_shift or librosa.effects.time_stretch on generated speech.

**Why bad:** Phase vocoder pitch shifting creates metallic artifacts. Time stretching via WSOLA introduces wavering. These are audible even at small ratios (0.9-1.1x) on clean speech.

**Instead:** Control pitch and timing through:
- Text-level punctuation injection (pauses)
- Emotion tags ([warm], [angry], etc.)
- Reference audio selection (the model replicates the reference's prosody)

## Scalability Considerations

Not applicable in the traditional sense (this is a single-GPU inference server, not a distributed system). But relevant concerns:

| Concern | Current State | With Humanism | Mitigation |
|---------|--------------|---------------|------------|
| Processing latency per chunk | ~0ms (just PeakFilter) | ~1-3ms (full chain on ~1s chunk) | Pedalboard is JUCE/C++, processes at 300x realtime. Negligible. |
| VRAM usage | Unchanged | Unchanged | All humanism processing is CPU numpy + pedalboard. Zero GPU cost. |
| Memory for IR convolution | 0 | ~500KB (one room IR loaded) | Convolution object loads IR once at init. |
| Code complexity | 3 lines (_post_fx definition) | ~50 lines (PauseInjector + saturate + expanded chain) | Each component is <20 lines, pure function, independently testable. |

## Sources

- [Spotify Engineering: Pedalboard](https://engineering.atspotify.com/2021/09/introducing-pedalboard-spotifys-audio-effects-library-for-python)
- [Pedalboard Examples](https://spotify.github.io/pedalboard/examples.html) -- chaining effects, streaming audio
- [Icon Collective: Mixing Effects Chain Order](https://www.iconcollective.edu/mixing-effects-chain-order)
- Fish Speech codebase: `fish_speech/inference_engine/__init__.py` lines 7, 25-27, 279
