# Domain Pitfalls: TTS Humanism & Naturalness

**Domain:** Speech post-processing and naturalness enhancement for neural TTS
**Researched:** 2026-04-13

## Critical Pitfalls

Mistakes that cause the output to sound worse than unprocessed, or require rework.

### Pitfall 1: Over-Processing (The "Radio DJ" Effect)

**What goes wrong:** Stacking compression + saturation + EQ + reverb with individually reasonable but cumulatively aggressive parameters. The speech sounds "produced" -- like a radio commercial or podcast intro -- rather than natural.

**Why it happens:** Each effect sounds fine in isolation. But their interactions multiply. Compression raises the noise floor, saturation adds harmonics, EQ boosts those harmonics, and reverb smears everything. The cumulative effect is unnatural.

**Consequences:** Listeners immediately perceive the speech as "processed" or "artificial" -- the opposite of the goal. Undoing this requires stripping back to baseline and re-tuning from scratch.

**Prevention:**
- Start every effect at bypass-equivalent parameters (gain_db=0, drive=0, mix=0)
- Increase one parameter at a time, A/B testing against unprocessed audio
- Rule of thumb: if you can distinctly hear an individual effect, it's too strong
- Total gain change across the chain should be < 3dB (compression gain reduction + EQ boosts + saturation harmonics)

**Detection:** Generate the same sentence with and without processing. If a listener can immediately tell which is processed (not "which sounds better," but "which has effects on it"), the processing is too heavy.

### Pitfall 2: Compressor State Across Streaming Chunks

**What goes wrong:** The Compressor (and to a lesser extent, Convolution) maintain internal state -- gain reduction envelope, convolution tail. If chunks are very short or if the audio characteristics change dramatically between chunks, the stateful effects produce artifacts at chunk boundaries.

**Why it happens:** A compressor's gain reduction ramps up during loud passages and releases during quiet ones. If chunk N ends mid-word and chunk N+1 starts mid-word, the compressor state from N carries into N+1 correctly. But if chunk N ends with silence and chunk N+1 starts with a loud onset, the compressor's attack time creates a brief period of too-loud audio before it catches up.

**Consequences:** Audible volume pumping at chunk boundaries. Brief loudness spikes at the start of chunks.

**Prevention:**
- Use gentle compression settings: ratio 2:1, attack 10ms, release 100ms. This minimizes the magnitude of gain-reduction swings.
- Pedalboard's process() method is designed for streaming -- it maintains state across calls. Do NOT recreate the Pedalboard object per chunk.
- The StreamingCrossfader already handles amplitude matching at boundaries; compression should be gentle enough to not fight it.
- If compression artifacts are audible, consider applying compression per-utterance (after all chunks are joined) rather than per-chunk.

**Detection:** Listen specifically at chunk boundaries. Compare with compressor bypassed. Volume pumping is most audible on transitions between silence and speech onset.

### Pitfall 3: Punctuation Injection Breaking Model Prosody

**What goes wrong:** Inserting punctuation (commas, semicolons) at positions where Fish Speech's text encoder interprets them differently than intended. The model generates unnatural pauses in the middle of phrases, or fails to generate pauses at intended points.

**Why it happens:** Fish Speech's DualAR transformer learns punctuation-to-prosody mapping from training data. If the training data rarely has commas after "however" but the PauseInjector adds one, the model may produce an awkwardly long pause or an unnatural pitch reset.

**Consequences:** Speech with weird pauses in wrong places sounds more robotic than speech with no added pauses at all. Users notice "wrong" pauses more than "missing" pauses.

**Prevention:**
- Start with minimal punctuation injection: only sentence-ending periods and obvious clause boundaries (before "and," "but," "or" in compound sentences)
- Test each punctuation rule independently with A/B listening
- Never inject punctuation mid-clause or mid-phrase
- Maintain a blocklist of contexts where injection harms prosody (discovered through testing)

**Detection:** Generate the same text with and without punctuation injection. Listen for unnatural pauses, pitch resets, or rhythm disruptions.

### Pitfall 4: Saturation Aliasing at 44.1kHz

**What goes wrong:** The tanh waveshaper generates harmonics that extend above the Nyquist frequency (22.05kHz at 44.1kHz sample rate). These alias back down into the audible range as inharmonic frequencies, producing a metallic or "digital" quality.

**Why it happens:** Nonlinear functions (tanh, x^2) create new frequency components at multiples of the input frequencies. Speech energy around 4-5kHz generates 3rd harmonics at 12-15kHz, 5th harmonics at 20-25kHz (above Nyquist), which alias.

**Consequences:** Subtle but audible metallic edge, especially on sibilants ("s", "sh", "z" sounds) which have energy up to 8-10kHz.

**Prevention:**
- Keep saturation drive very low (0.2-0.3). At low drive, harmonic levels are well below the noise floor.
- If aliasing is audible, add 2x oversampling: upsample to 88.2kHz, saturate, then downsample. This pushes aliases above the audible range.
- The HighShelfFilter at 8kHz with modest gain (+1dB) partially compensates by not boosting the aliased region further.
- Alternative: use Chebyshev polynomial waveshaping which allows controlling individual harmonic levels, preventing high-order harmonics from reaching significant levels.

**Detection:** Compare saturated vs. unsaturated on sibilant-heavy text ("She sells seashells by the seashore"). Metallic or harsh sibilants indicate aliasing.

## Moderate Pitfalls

### Pitfall 5: Wrong Room IR Sounds Worse Than No Room IR

**What goes wrong:** Using an impulse response with too long an RT60, too distant a mic position, or room characteristics that don't match the "someone speaking to you" expectation. Speech sounds like it's in a bathroom, church, or large hall.

**Prevention:**
- Only use IRs with RT60 < 0.3 seconds
- Only use close-mic perspective IRs
- Start with Convolution mix at 0.02 (2%) and increase gradually
- A/B test against no-IR version -- if the reverb tail is audible on speech, it's too much

### Pitfall 6: EQ Boost Without Corresponding Headroom

**What goes wrong:** Adding LowShelfFilter (+2dB) + PeakFilter (+1.5dB) + HighShelfFilter (+1dB) = +4.5dB cumulative boost. Audio clips before the Limiter catches it, or the Limiter works too hard and introduces pumping.

**Prevention:**
- Add a `Gain(gain_db=-3.0)` at the start of the chain to create headroom
- Or keep total boost under +3dB
- The Limiter at -1dB threshold is the safety net, but it should rarely activate. If it's constantly limiting, reduce upstream gains.

### Pitfall 7: Measuring Prosody on Processed Audio

**What goes wrong:** Running PyWorld F0 analysis on audio that has already been through the post-FX chain. Saturation and EQ change the harmonic structure, which can affect F0 extraction accuracy.

**Prevention:**
- Always run PyWorld on raw DAC decoder output, before any post-processing
- Store raw audio alongside processed audio during development for clean analysis
- F0 measurements on processed audio are unreliable, especially after saturation

### Pitfall 8: Silence Detection Threshold Mismatch

**What goes wrong:** Audio-level pause injection uses a silence threshold (e.g., -40dB) calibrated for one speaker/emotion but applied to all. Angry speech is louder, whispered speech is quieter. A fixed threshold either misses pauses in loud speech or falsely detects pauses in quiet speech.

**Prevention:**
- Use relative thresholds based on the audio segment's RMS energy, not absolute dB values
- Or rely primarily on text-level pause injection (which is threshold-independent)
- If audio-level detection is needed, use adaptive thresholding: silence = below 15-20% of the segment's peak amplitude

## Minor Pitfalls

### Pitfall 9: Convolution IR Sample Rate Mismatch

**What goes wrong:** The IR WAV file is at 48kHz or 96kHz but the audio is at 44.1kHz. Pedalboard's Convolution may resample internally, but this adds subtle latency and potential quality loss.

**Prevention:** Pre-resample IR files to 44.1kHz to match DAC output. Store them as 32-bit float WAV for best quality.

### Pitfall 10: Asymmetric Saturation DC Offset

**What goes wrong:** The asymmetric term (`asymmetry * x^2`) shifts the output's DC component. Over time or after multiple processing passes, DC offset accumulates and reduces headroom.

**Prevention:** Add DC blocking after saturation. Simple approach: `audio = audio - np.mean(audio)`. Or use a high-pass filter at 20Hz (pedalboard HighpassFilter).

### Pitfall 11: Parameter Tuning Subjectivity

**What goes wrong:** Developers tune parameters to their own headphones/speakers/preferences. What sounds warm on studio monitors sounds muddy on earbuds. What sounds crisp on headphones sounds harsh on laptop speakers.

**Prevention:**
- Test on at least 3 playback devices: headphones, laptop speakers, phone speakers
- Use pyworld F0 metrics as objective (device-independent) quality checks
- Document parameter choices with rationale, not just "sounds good to me"

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Text-level pause injection | Pitfall 3: Wrong punctuation placement breaks prosody | Start minimal, test each rule independently |
| Post-FX chain expansion | Pitfall 1: Over-processing, Pitfall 6: Headroom | Start at bypass, increase one param at a time |
| Soft saturation | Pitfall 4: Aliasing, Pitfall 10: DC offset | Low drive, DC blocking, test on sibilants |
| Room convolution | Pitfall 5: Wrong IR, Pitfall 9: Sample rate mismatch | Short dry IRs, pre-resample to 44.1kHz |
| Prosody measurement | Pitfall 7: Measuring processed audio | Always analyze raw DAC output |
| Streaming interaction | Pitfall 2: Compressor state at chunk boundaries | Gentle settings, don't recreate Pedalboard per chunk |

## Sources

- [Stanford CCRMA: Soft Clipping](https://ccrma.stanford.edu/~jos/pasp/Soft_Clipping.html) -- aliasing in nonlinear processing
- [musicdsp.org: Variable Hardness Clipping](https://www.musicdsp.org/en/latest/Effects/104-variable-hardness-clipping-function.html) -- anti-aliasing via oversampling
- [Sage Audio: Vocal Effect Chaining](https://www.sageaudio.com/articles/how-to-chain-vocal-effects) -- chain ordering and headroom management
- [Mastering Chain Order](https://audiospectra.net/mastering-chain-order/) -- gain staging principles
- [LANDR: Vocal Compression](https://blog.landr.com/vocal-compression/) -- compression ratio and attack/release guidelines
- Fish Speech codebase: existing _post_fx behavior observed in `inference_engine/__init__.py`
