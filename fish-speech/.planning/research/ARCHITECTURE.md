# Architecture: TTS Humanism Integration Points

**Domain:** Natural speech realism for Fish Speech S2-Pro TTS engine
**Researched:** 2026-04-13
**Confidence:** HIGH (based on direct codebase analysis of every integration point)

## Pipeline Overview (Current State)

```
Request
  |
  v
[1] ServeTTSRequest (schema.py)
  |
  v
[2] TTSInferenceEngine.inference() (__init__.py)
  |
  +---> [3] send_Llama_request() --> llama_queue --> worker thread
  |           |
  |           v
  |     [4] generate_long() (inference.py)
  |           |
  |           +---> [5] split_text_into_chunks() (inference.py:760-808)
  |           |
  |           +---> For each text batch:
  |           |       +---> [6] Build Conversation, encode_for_inference()
  |           |       +---> [7] generate() --> decode_n_tokens() --> DualAR tokens
  |           |       +---> yield GenerateResponse(codes=..., is_partial=True/False)
  |           |
  |           +---> yield GenerateResponse(action="next")
  |
  +---> [8] get_audio_segment() (__init__.py:261-279)
  |           |
  |           +---> [9] decode_vq_tokens() --> DAC.from_indices() --> raw tensor
  |           +---> [10] float().cpu().numpy()
  |           +---> [11] _post_fx(audio, sr) --> PeakFilter(3500Hz, +1.5dB, q=0.7)
  |
  +---> [12] Sub-chunk streaming: grow-and-redecode with sin^2 crossfade
  |     OR:   StreamingCrossfader.process() (crossfader.py)
  |
  +---> [13] yield InferenceResult(code="segment", audio=(sr, numpy_array))
  |
  v
[14] inference_wrapper() (tools/server/inference.py)
  |
  +---> [15] (audio * 32768).astype(np.int16).tobytes()
  |
  v
[16] inference_async() --> HTTP chunked response (api_utils.py:72-92)
```

## Technique-to-Integration-Point Map

### 1. Dynamic Pause Injection

**Where:** Two viable insertion points, with different tradeoffs.

#### Option A: Text-level (RECOMMENDED -- easiest, most natural)

**File:** `fish_speech/models/text2semantic/inference.py`
**Function:** `split_text_into_chunks()` (lines 760-808)
**Hook point:** After Phase 3 (emotion propagation, line 808), add a Phase 4 that analyzes chunk boundaries and annotates pause durations.

**Mechanism:** Insert extra punctuation or SSML-style pause markers into text chunks before they enter the LLM. The DualAR model already produces natural pauses at punctuation -- a period produces roughly 200-400ms of near-silence in the generated audio. By manipulating punctuation (e.g., adding `...` for longer pauses, or `--` for mid-sentence hesitations), you control pause duration at the model level without touching audio.

**Alternatively:** A new function `inject_pauses(chunks: list[str]) -> list[str]` called from `generate_long()` at line 900, right after `split_text_into_chunks()` returns its chunk list and before the batches enter the generation loop.

**Constraints:**
- Must happen BEFORE tokens enter the LLM (before line 919's batch loop)
- Punctuation-based pauses are approximate -- the model decides final duration
- Cannot insert pauses mid-word or at sub-phoneme granularity this way

#### Option B: Audio-level silence insertion

**File:** `fish_speech/inference_engine/__init__.py`
**Function:** `inference()` (lines 97-221)
**Hook point:** Between get_audio_segment() return (line 279) and the yield of InferenceResult (lines 142-147 for sub-chunk, or lines 174-182 for crossfader path).

**Mechanism:** After decoding audio for a chunk, prepend or append `np.zeros(pause_samples, dtype=np.float32)` to the audio array before yielding. The pause duration maps directly to sample count: `pause_ms * 44.1` samples.

**Specific insertion code path (sub-chunk mode):**
```
Line 127: new_audio = segment[prev_audio_samples:]
    --> Insert silence AFTER this line, BEFORE the crossfade check at line 129
    --> new_audio = np.concatenate([np.zeros(pause_samples), new_audio])
```

**Specific insertion code path (crossfader mode):**
```
Line 174: segment = self.get_audio_segment(result)
    --> Insert silence BEFORE crossfader.process()
    --> segment = np.concatenate([np.zeros(pause_samples), segment])
```

**Constraints:**
- Must happen BEFORE crossfade blending (silence in the crossfade region would be faded away)
- Audio-level pauses sound mechanical unless shaped (fade-in from silence)
- Adds to total audio length, which is fine for streaming but affects the "final" concatenation at line 216

**Recommendation:** Use Option A (text-level) as primary. Use Option B only for precise sub-sentence pauses that the model cannot learn from punctuation (e.g., dramatic pauses mid-clause).

---

### 2. Prosody / Pitch Modification

**Where:** This CANNOT meaningfully happen at the token level without model retraining. Must happen post-decode in the audio domain.

**Why not token-level:** The DualAR transformer generates semantic tokens that map to VQ codebook indices. These indices encode a compressed representation of the audio (pitch + timbre + phoneme identity all entangled). There is no "pitch knob" at the token level -- modifying token values would produce garbled audio, not pitch-shifted audio. Prosody is implicitly learned from the reference audio and text context.

**File:** `fish_speech/inference_engine/__init__.py`
**Function:** `get_audio_segment()` (lines 261-279)
**Hook point:** Line 278-279, after DAC decode and before _post_fx, or integrated into the _post_fx chain.

**Current code:**
```python
# Line 275-279
audio = segment.float().cpu().numpy()
if hasattr(self.decoder_model, "spec_transform"):
    sr = self.decoder_model.spec_transform.sample_rate
else:
    sr = self.decoder_model.sample_rate
return self._post_fx(audio, sr)
```

**Mechanism:** Use `pedalboard.PitchShift` (already available in the pedalboard library, which is an existing dependency). Apply subtle pitch variation per-segment to avoid the monotone "same pitch contour for every sentence" problem.

**Implementation approach:**
```python
# In get_audio_segment(), before return:
audio = segment.float().cpu().numpy()
sr = ...
# Apply prosody variation BEFORE the EQ chain
audio = self._prosody_fx(audio, sr)  # pitch shift, etc.
return self._post_fx(audio, sr)
```

**Constraints:**
- Pitch shifting on short segments (< 1s) can produce artifacts at segment boundaries
- Must happen BEFORE crossfade -- if you pitch-shift after crossfade, the blended region will have mismatched pitch
- `pedalboard.PitchShift` operates on numpy arrays and is fast (C++ backend via JUCE)
- Aggressive pitch shifting (> +/- 2 semitones) will sound artificial. Target range: +/- 0.3 semitones for subtle warmth variation
- The shift amount should vary per chunk (not per sub-chunk), driven by text analysis (questions pitch up, statements pitch down, trailing clauses pitch down slightly)

**Alternative for speech rate variation (see section 5):** Time-stretching can also happen here, but pedalboard does not have a native time-stretch effect. Would need `python-stretch` or `pyrubberband`.

---

### 3. Breathing Sounds

**Where:** Audio-level mixing, inserted between segments.

**Approach:** Pre-recorded breath samples mixed into the audio stream. Synthesized breaths are possible but require significant modeling effort for minimal gain over well-recorded samples.

**File:** `fish_speech/inference_engine/__init__.py`
**Function:** `inference()` (lines 97-221)
**Hook point:** Same as pause injection Option B -- between `get_audio_segment()` and the yield.

**Specific insertion points (two cases):**

**Case 1: Between text batches (chunk boundaries)**

In the sub-chunk path, at the batch boundary transition (lines 150-170):
```
Line 157: new_audio = segment[prev_audio_samples:]
    --> At batch boundary (is_partial=False), prepend a breath sample:
    --> breath = load_breath_sample(breath_type, sr)  # cached
    --> body = np.concatenate([breath, new_audio[:-overlap]])
```

In the crossfader path (lines 171-182):
```
Line 174: segment = self.get_audio_segment(result)
    --> segment = np.concatenate([breath_sample, segment])
    --> THEN pass to crossfader
```

**Case 2: Within a batch (at sentence boundaries detected from text)**

This requires knowing where sentence boundaries fall within a single audio segment. Since each `GenerateResponse` corresponds to one text batch, and batches may contain multiple sentences, mid-batch breath insertion is harder.

**Better approach:** Let the text chunker split at sentence boundaries (it already does in `split_text_into_chunks()`), and insert breaths at every chunk transition. This means breaths happen at natural sentence boundaries.

**Breath sample management:**
- Pre-record 5-10 breath variations (inhale, soft exhale, quick breath) at 44100Hz mono float32
- Store as `.npy` files in a `resources/breaths/` directory
- Load and cache at engine initialization
- Randomly select per-insertion for variation
- Apply volume scaling (breaths should be 15-25dB below speech level)
- Apply fade-in/fade-out (5ms) to avoid clicks

**Constraints:**
- Breath samples must match the reference voice's timbre to sound natural. Generic breaths may sound jarring with a specific voice.
- Must happen BEFORE crossfade -- the breath is part of the segment that gets crossfaded
- Breath duration adds to total audio length (typical: 150-400ms, i.e., 6600-17640 samples at 44100Hz)
- Not every boundary needs a breath. Use a probability-based approach: 60% chance after sentences, 20% after clauses, 0% for sub-chunk partials.

---

### 4. Post-Processing Chain (Warmth/Presence)

**Where:** Expand the existing `_post_fx` Pedalboard chain.

**File:** `fish_speech/inference_engine/__init__.py`
**Class attribute:** `_post_fx` (line 25-27)
**Current state:**
```python
_post_fx = Pedalboard([
    PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7),
])
```

**Recommended expanded chain:**

```python
from pedalboard import (
    Pedalboard, PeakFilter, Compressor, Gain,
    LowShelfFilter, HighShelfFilter, HighpassFilter,
)

_post_fx = Pedalboard([
    # 1. Subsonic rumble removal (DAC decoder can produce low-freq artifacts)
    HighpassFilter(cutoff_frequency_hz=80),

    # 2. Warmth: gentle low-mid boost
    LowShelfFilter(cutoff_frequency_hz=250, gain_db=1.5, q=0.7),

    # 3. Presence: existing brightness boost (unchanged)
    PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7),

    # 4. Air: subtle high-frequency lift for clarity
    HighShelfFilter(cutoff_frequency_hz=8000, gain_db=1.0, q=0.7),

    # 5. Gentle compression: reduces volume spikes, adds consistency
    Compressor(threshold_db=-18, ratio=2.5, attack_ms=10, release_ms=100),

    # 6. Makeup gain (compression reduces overall level)
    Gain(gain_db=2.0),
])
```

**Constraints:**
- This runs on EVERY audio segment, including sub-chunk partials. Must be fast.
- Pedalboard processes numpy arrays in C++ -- a 1-second segment at 44100Hz takes < 1ms. No streaming concern.
- The Compressor has state (attack/release envelope). For streaming with sub-chunk partials, the compressor state resets per `get_audio_segment()` call. This means the first few ms of each segment have no compression history. At segment sizes of 500ms+, this is inaudible.
- **Critical:** The compressor must come AFTER EQ, not before. Boosting frequencies then compressing prevents the compressor from fighting the EQ.
- Do NOT add Reverb to the chain. Reverb tails would bleed across chunk boundaries and produce artifacts with crossfading. If reverb is desired, it must be applied as a final pass on the complete concatenated audio (the "final" InferenceResult), not on individual segments.

**Where applied:** `get_audio_segment()` line 279: `return self._post_fx(audio, sr)`. No change to calling code needed -- just expand the `_post_fx` chain.

---

### 5. Speech Rate Variation

**Where:** Three options with different tradeoff profiles.

#### Option A: Text-level (chunk size hints) -- SIMPLEST

**File:** `fish_speech/models/text2semantic/inference.py`
**Function:** `split_text_into_chunks()` (lines 760-808)

**Mechanism:** Vary the `subsequent_chunk_bytes` parameter per-chunk based on text analysis. Shorter chunks produce faster-feeling speech (more frequent pauses). Longer chunks produce more flowing speech. This is crude but zero-risk.

#### Option B: Token-level (temperature variation) -- MODERATE COMPLEXITY

**File:** `fish_speech/models/text2semantic/inference.py`
**Function:** `generate_long()` (line 988, the `temperature=temperature` kwarg to `generate()`)

**Mechanism:** Vary the temperature parameter per text batch. Higher temperature = more variation in token selection = more expressive (but potentially less stable) speech. Lower temperature = more predictable, measured speech.

**Constraints:** Temperature affects quality and consistency, not just speed. Must stay within safe range (0.6-0.95). This is a blunt instrument.

#### Option C: Audio-level time-stretching -- MOST CONTROL, MOST RISK

**File:** `fish_speech/inference_engine/__init__.py`
**Function:** `get_audio_segment()` (lines 261-279)
**Hook point:** After DAC decode, before _post_fx (same location as pitch modification).

**Mechanism:** Use `python-stretch` (Signalsmith Stretch) or `pyrubberband` for per-segment time-stretching. Stretch factor 0.95 = 5% faster, 1.05 = 5% slower.

**Constraints:**
- Time-stretching changes segment length, which breaks the sub-chunk grow-and-redecode math. The `prev_audio_samples` counter (line 125) tracks cumulative audio length for the grow-and-redecode window. If segments change length due to stretching, the offset calculations become wrong.
- Time-stretching MUST happen AFTER the full chunk is decoded (is_partial=False path), not during sub-chunk partials.
- Adds a new dependency (python-stretch or pyrubberband). pyrubberband writes to disk (slow). python-stretch is native and fast.
- Must happen BEFORE crossfade.

**Recommendation:** Start with Option A (text-level chunk sizing). Graduate to Option C only if noticeable monotonous pacing remains. Option B (temperature variation) is a last resort due to quality risk.

---

### 6. Volume Dynamics / Gain Automation

**Where:** Two integration points.

#### Per-segment volume (sentence-level dynamics)

**File:** `fish_speech/inference_engine/__init__.py`
**Function:** `get_audio_segment()` (lines 261-279)
**Hook point:** After DAC decode, as part of the post-processing. Can be integrated into the `_post_fx` chain or applied separately.

**Mechanism:** Analyze the text content for each batch (available from `GenerateResponse.text`), and apply a gain multiplier. Parenthetical text or trailing clauses get -1 to -3 dB. Emphasized text gets +1 dB. Questions get a slight overall boost.

**Problem:** `get_audio_segment()` does not currently receive the text content -- it only receives `GenerateResponse` which has `.codes` and `.text`. The `.text` field IS available.

**Implementation:**
```python
# In inference(), where get_audio_segment is called:
# Line 123: segment = self.get_audio_segment(result)
# Change to pass text context:
segment = self.get_audio_segment(result, text_hint=result.text)
```

Then in `get_audio_segment()`:
```python
def get_audio_segment(self, result: GenerateResponse, text_hint: str = "") -> np.ndarray:
    # ... existing decode ...
    audio = segment.float().cpu().numpy()
    # Apply text-driven gain
    gain_db = self._compute_text_gain(text_hint)
    audio = audio * (10 ** (gain_db / 20))
    return self._post_fx(audio, sr)
```

#### Within-segment volume (word-level dynamics via compression)

Already handled by the Compressor in the expanded `_post_fx` chain (section 4). The compressor reduces peaks and raises quieter passages, creating more even volume with natural-sounding dynamics.

**Constraints:**
- Per-segment gain must be subtle (max +/- 3 dB) to avoid noticeable volume jumps at chunk boundaries
- The crossfader blends audio at boundaries, so a sudden volume change between segments will create an audible ramp during the crossfade region. Keep gains smooth.
- If using sub-chunk streaming, gain must be consistent within a single text batch (all sub-chunks of one batch get the same gain)

---

## Component Boundary Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TEXT DOMAIN                                   │
│                                                                     │
│  [A] Text Preprocessor (NEW)                                       │
│      - Pause injection via punctuation manipulation                 │
│      - Chunk size variation for speech rate                         │
│      - Sentence analysis for downstream volume hints                │
│                                                                     │
│  Location: inference.py, between split_text_into_chunks()           │
│            and the generate_long() batch loop                       │
│                                                                     │
│  Input:  list[str] (text chunks)                                    │
│  Output: list[str] (modified text chunks with pause markers)        │
│          + dict[int, HumanismHints] (per-chunk metadata)            │
├─────────────────────────────────────────────────────────────────────┤
│                        TOKEN DOMAIN                                  │
│                                                                     │
│  [B] Generation Parameters (EXISTING, minor modification)           │
│      - Per-batch temperature variation (optional)                   │
│                                                                     │
│  Location: generate_long() batch loop, line 988                     │
│                                                                     │
│  Input:  HumanismHints for current batch                            │
│  Output: Modified temperature/top_p for generate() call             │
├─────────────────────────────────────────────────────────────────────┤
│                        AUDIO DOMAIN                                  │
│                                                                     │
│  [C] Audio Post-Processor (EXPANDED from existing _post_fx)        │
│      - EQ chain: HPF -> warmth -> presence -> air                  │
│      - Dynamics: compressor -> makeup gain                         │
│      - Pitch variation: subtle per-segment shift                   │
│      - Volume automation: text-driven gain adjustment              │
│                                                                     │
│  Location: get_audio_segment() in __init__.py                      │
│                                                                     │
│  Input:  raw DAC output tensor + text hint                          │
│  Output: processed numpy float32 array                              │
│                                                                     │
│  [D] Breath Inserter (NEW)                                         │
│      - Pre-recorded breath sample mixing                            │
│      - Probability-based insertion at chunk boundaries              │
│                                                                     │
│  Location: inference() main loop, between get_audio_segment()       │
│            and crossfade/yield                                      │
│                                                                     │
│  Input:  processed audio segment + chunk boundary info              │
│  Output: audio segment with optional breath prepended               │
│                                                                     │
│  [E] Silence Inserter (NEW, optional)                              │
│      - Precise audio-level pause insertion                          │
│      - Shaped silence (fade envelope, not hard zeros)              │
│                                                                     │
│  Location: inference() main loop, same as [D]                       │
│                                                                     │
│  Input:  audio segment + pause duration from HumanismHints         │
│  Output: audio segment with silence prepended/appended              │
├─────────────────────────────────────────────────────────────────────┤
│                        STREAMING DOMAIN (unchanged)                  │
│                                                                     │
│  [F] Crossfader (EXISTING -- StreamingCrossfader)                  │
│      - sin^2 equal-power blending                                  │
│      - No changes needed, operates on whatever audio it receives   │
│                                                                     │
│  [G] Stream Emitter (EXISTING -- inference_wrapper)                │
│      - int16 conversion, HTTP chunked response                     │
│      - No changes needed                                            │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow (With Humanism Hooks)

```
Request text: "Hello, how are you? I'm doing well, thanks for asking."
    |
    v
[A] Text Preprocessor:
    - Split into chunks: ["Hello, how are you?", "I'm doing well, thanks for asking."]
    - Analyze: chunk[0] is a question, chunk[1] is a statement
    - Generate hints: {0: {gain: +0.5dB, pitch: +0.2st, breath_after: 0.7},
                       1: {gain: -0.5dB, pitch: -0.1st, breath_after: 0.3}}
    - Optionally insert pause markers: "Hello... how are you?"
    |
    v
[B] Token Generation (per batch):
    - Batch 0: temperature=0.85 (default)
    - Batch 1: temperature=0.82 (slightly lower for calmer statement)
    |
    v
[7] DualAR generates VQ codes for each batch
    |
    v
[C] Audio Post-Processor (per segment):
    - DAC decode: codes -> raw waveform
    - Pitch shift: +0.2 semitones (batch 0, question)
    - EQ chain: HPF(80) -> LowShelf(250, +1.5dB) -> Peak(3500, +1.5dB)
               -> HighShelf(8000, +1.0dB)
    - Compressor: threshold -18dB, ratio 2.5:1
    - Gain: +2dB makeup + text-driven +0.5dB
    |
    v
[D] Breath Inserter (at batch boundary):
    - Roll dice: 0.7 probability -> YES, insert breath
    - Select random breath sample (150ms)
    - Scale to -20dB relative to speech RMS
    - Prepend to segment
    |
    v
[12] Crossfader:
    - Blends breath tail of segment N with head of segment N+1
    - sin^2 equal-power, 1764 samples overlap
    |
    v
[13-16] Yield -> int16 -> HTTP
```

## Ordering Constraints (What Must Happen Before What)

```
Text Domain:    [A] pause injection + chunk analysis
                    |
                    v
Token Domain:   [B] generation with hints
                    |
                    v
Audio Domain:   [9] DAC decode (untouchable)
                    |
                    v
                [C.pitch] pitch shift (if any)   <-- BEFORE EQ/compression
                    |
                    v
                [C.eq] EQ chain (HPF, shelves, peak)
                    |
                    v
                [C.dynamics] compressor + gain
                    |
                    v
                [D/E] breath/silence insertion    <-- AFTER post-fx, BEFORE crossfade
                    |
                    v
                [F] crossfade blending           <-- MUST be last audio operation
                    |
                    v
                [G] int16 conversion + stream     <-- AFTER crossfade
```

**Critical ordering rules:**
1. Pitch shift BEFORE EQ/compression. Shifting after compression would undo the compressor's envelope.
2. All audio modifications BEFORE crossfade. Crossfade operates on the final audio; any post-crossfade modification would create discontinuities at blend points.
3. Breath insertion BEFORE crossfade. The breath becomes part of the segment that gets blended smoothly.
4. Compression AFTER EQ. The EQ shapes the spectrum; the compressor then manages the dynamics of the shaped signal.
5. Silence insertion can happen before OR after breath insertion (silence then breath = pause then inhale, which is natural).

## Difficulty Assessment

| Technique | Difficulty | Risk to Streaming | Files Modified | New Dependencies |
|-----------|-----------|-------------------|----------------|-----------------|
| Post-FX chain expansion | Easy | None | `__init__.py` only | None (pedalboard already present) |
| Text-level pause injection | Easy | None | `inference.py` only | None |
| Volume dynamics (per-segment) | Easy | None | `__init__.py` only | None |
| Breathing sounds | Medium | Low | `__init__.py` + new resource files | None (numpy only) |
| Audio-level silence insertion | Easy | Low | `__init__.py` only | None |
| Pitch variation (pedalboard) | Medium | Low | `__init__.py` only | Need to verify `PitchShift` available in installed version |
| Speech rate (text-level) | Easy | None | `inference.py` only | None |
| Speech rate (time-stretch) | Hard | Medium | `__init__.py`, breaks sub-chunk math | `python-stretch` or `pyrubberband` |
| Temperature variation | Easy | Low (quality risk) | `inference.py` only | None |

## Suggested Build Order (Dependencies)

```
Phase 1: Post-FX Chain        [C.eq + C.dynamics]     -- No dependencies, immediate quality win
    |
Phase 2: Text Preprocessor    [A]                      -- No audio deps, text-only
    |
    v
Phase 3: Pause Injection      [A -> audio silence]     -- Depends on Phase 2 for hints
    |
Phase 4: Breathing Sounds     [D]                      -- Independent, but benefits from Phase 2's boundary data
    |
Phase 5: Volume Dynamics      [C.gain]                 -- Depends on Phase 2 for text analysis
    |
Phase 6: Pitch Variation      [C.pitch]                -- Most experimental, do last
```

**Rationale:**
- Phase 1 is the easiest win: modifying a single class attribute in `__init__.py` with no risk to streaming. Immediate warmth/presence improvement.
- Phase 2 is text-only, no audio risk. Creates the infrastructure (HumanismHints) that Phases 3-5 consume.
- Phases 3-4 are the biggest perceptual improvements (pauses and breathing make speech sound human).
- Phase 5 is subtle refinement.
- Phase 6 (pitch) is most likely to introduce artifacts and should be done last with careful A/B testing.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Modifying Audio After Crossfade
**What:** Applying pitch shift, EQ, or gain after the crossfader has blended segments.
**Why bad:** The crossfade region contains blended samples from two segments. Any modification to the blended audio (especially pitch shifting or time-stretching) will create artifacts because the blend assumes waveform continuity.
**Instead:** All audio processing happens in `get_audio_segment()` BEFORE the segment enters the crossfade pipeline.

### Anti-Pattern 2: Reverb on Individual Segments
**What:** Adding reverb to the `_post_fx` chain that runs per-segment.
**Why bad:** Reverb tails extend 200-2000ms beyond the dry signal. When segment N's reverb tail bleeds into the crossfade region, it gets blended with segment N+1's start, creating a doubled/phased reverb artifact.
**Instead:** If reverb is desired, apply it ONLY to the final concatenated audio (the `InferenceResult(code="final")` path at line 216-220), not to individual segments. For streaming, reverb cannot be used.

### Anti-Pattern 3: Time-Stretching Sub-Chunk Partials
**What:** Applying time-stretching to sub-chunk partial audio segments (is_partial=True).
**Why bad:** The grow-and-redecode strategy in the sub-chunk path tracks `prev_audio_samples` to slice only the new audio from each growing decode. Time-stretching changes the sample count, making the `segment[prev_audio_samples:]` slice incorrect -- you'd either skip audio or double-emit audio.
**Instead:** If time-stretching is needed, apply it only to the final audio of each text batch (is_partial=False path) after all sub-chunks have been accumulated.

### Anti-Pattern 4: Stateful Effects Across Segments Without Reset Awareness
**What:** Using effects with long state memory (e.g., a compressor with 500ms release) across independent segments without considering state discontinuity.
**Why bad:** Each `get_audio_segment()` call creates a fresh audio array. The compressor has no memory of the previous segment's level. If the previous segment ended loud and this one starts quiet, the compressor won't apply the expected gain reduction for the first ~release_ms.
**Instead:** Use short attack/release times (attack 5-15ms, release 50-150ms) so the compressor reaches steady state quickly within each segment. Alternatively, maintain a shared `Pedalboard` instance with persistent state, but this requires careful handling of the streaming pipeline.

### Anti-Pattern 5: Generic Breath Samples
**What:** Using a single breath recording for all insertions.
**Why bad:** Identical breaths at every pause sound robotic. Humans vary their breathing.
**Instead:** Maintain a pool of 5-10 breath variations. Randomize selection. Vary volume by +/- 3dB. Vary timing slightly (prepend 0-50ms of silence before the breath).

## Sources

- Codebase analysis of `/home/prana/project-seishin/fish-speech/` -- HIGH confidence, direct code reading of all integration points
- [Spotify Pedalboard v0.9.22 API](https://spotify.github.io/pedalboard/reference/pedalboard.html) -- HIGH confidence, effects available: Compressor, LowShelfFilter, HighShelfFilter, PeakFilter, HighpassFilter, Gain, PitchShift
- [Semicolon Injection for Natural TTS Pauses (2026)](https://bagrounds.org/ai-blog/2026-03-10-tts-semicolon-injection) -- MEDIUM confidence, text-level pause technique
- [Google Patent US9508338B1: Inserting Breath Sounds into TTS](https://patents.google.com/patent/US9508338B1/en) -- HIGH confidence, established technique
- [Amazon Polly SSML Breath Feature](https://aws.amazon.com/blogs/machine-learning/amazon-polly-releases-new-ssml-breath-feature/) -- HIGH confidence, industry standard
- [python-stretch (Signalsmith Stretch)](https://pypi.org/project/python-stretch/) -- MEDIUM confidence, streaming-compatible time-stretch
- [Rubber Band Library v4.0](https://breakfastquay.com/rubberband/) -- HIGH confidence, native pitch/time manipulation
- [Apple Research: Controllable Neural TTS (NAACL 2025)](https://machinelearning.apple.com/research/controllable-neural-text-to-speech-synthesis) -- MEDIUM confidence, confirms prosody must be controlled at model level or post-hoc in audio domain
- [Duration-Aware Pause Insertion (arXiv 2302.13652)](https://arxiv.org/abs/2302.13652) -- MEDIUM confidence, academic validation of pause insertion importance
- [Kokoro-82M Silence Insertion via np.zeros](https://huggingface.co/hexgrad/Kokoro-82M/discussions/61) -- MEDIUM confidence, community-validated approach
