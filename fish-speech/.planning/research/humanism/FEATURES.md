# Feature Landscape: TTS Humanism & Naturalness

**Domain:** Making neural TTS output sound human-like
**Researched:** 2026-04-13

## Table Stakes

Features that listeners subconsciously expect from natural-sounding speech. Missing = speech sounds "robotic" or "flat."

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Natural pause timing** | Humans pause at clause boundaries, between thoughts, before important words. Monotonous timing without pauses is the #1 giveaway of synthetic speech. | Low | Text-level punctuation injection. Fish Speech already maps punctuation to pauses. Cost: regex + string manipulation. |
| **Pitch variation** | Monotone pitch is immediately perceived as robotic. Natural speech has 20-60 Hz F0 standard deviation. TTS models tend toward "average" prosody (implicit prosody modeling collapses to mean). | Low-Med | Primarily addressed by emotion tags and reference audio quality. Measurement via pyworld confirms effectiveness. |
| **Dynamic range** | Human speech has natural volume variation -- emphasis, trailing off, loudness shifts. Raw TTS output is often too uniform in loudness. | Low | Gentle compression (2:1 ratio) + limiter. Pedalboard Compressor. |
| **Tonal warmth** | Unprocessed digital audio sounds "cold" or "clinical." Human voice heard through air/microphone has natural harmonic richness from vocal tract resonance. | Low | LowShelfFilter boost + subtle saturation. Already partially addressed by PeakFilter. |

## Differentiators

Features that set the output apart as notably human-like. Not expected in baseline TTS, but noticed when present.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Room presence** | Speech that sounds like it's happening "in a room" vs. "in a digital void." Subtle room coloration triggers subconscious familiarity. | Low-Med | Convolution with short room IR at very low mix (2-5%). Pedalboard Convolution + static WAV asset. |
| **Breath-space timing** | Pauses long enough for a natural breath cycle (~300-500ms at sentence boundaries). Not synthetic breath sounds, but correctly-timed silence that implies breathing. | Low | Text-level: ensure sentence-ending punctuation exists. Audio-level: verify pause durations at detected silence segments. |
| **High-frequency "air"** | Subtle high-shelf boost above 8kHz adds the perception of "hearing someone breathe" and the sibilant detail of close-mic speech. | Low | HighShelfFilter at 8kHz, +1dB. Pedalboard. |
| **Trailing off / sentence-ending softness** | Human speech naturally reduces in volume and pitch at phrase endings. TTS often maintains constant energy to the last phoneme. | Med | Primarily model behavior (emotion tags, reference audio). Can be enhanced with amplitude envelope shaping on detected phrase-final segments. |
| **Variable speech rate** | Humans speed up through familiar/unimportant phrases and slow down for emphasis or new information. Constant rate sounds robotic. | Med | Primarily model behavior. Text-level: shorter words/simpler syntax for fast sections, longer pauses around important content. Not addressable in post-processing without time-stretching artifacts. |
| **Micro-pauses at punctuation** | Brief hesitations (50-150ms) at commas, semicolons, and colons that are shorter than full pauses but longer than nothing. | Low | Already handled by Fish Speech's response to punctuation. Verify with pyworld pause detection. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Synthetic breath sound injection** | No Python library produces convincing breath sounds. Amazon Polly's `<amazon:breath>` is proprietary. Post-hoc synthetic breaths sound worse than the model's natural ones. | Ensure reference audio has natural breathing. Let the model generate breaths from training data. |
| **Vocal fry / creaky voice synthesis** | Requires glottal pulse modeling (LF model + LPC) -- significant engineering for a niche effect. Vocal fry is culturally specific and sounds artificial when synthesized. | If vocal fry is desired, use reference audio that exhibits vocal fry. The model will replicate it. |
| **Heavy reverb / echo** | Makes speech hard to understand. Reverb >0.3s RT60 sounds like a bathroom or cave, not a natural speaking environment. | Use Convolution with short, dry room IRs at very low mix (2-5%). |
| **Pitch shifting post-hoc** | Phase vocoder pitch shift (torchaudio, librosa) introduces metallic artifacts. Sounds worse than the model's natural pitch. | Control pitch through emotion tags and reference audio selection. |
| **Time stretching post-hoc** | WSOLA/phase vocoder time stretching degrades audio quality. Sounds "processed" even at small ratios. | Control speech rate through text structure (shorter sentences = faster perceived rate). |
| **Aggressive compression** | Ratio >4:1 squashes dynamics flat. Sounds like a radio commercial, not a human. | Gentle compression: 2:1 ratio, -20dB threshold, 10ms attack. |
| **Multi-band processing** | Splitting speech into frequency bands for independent processing is overkill and risks phase issues at crossover points. | Single-band processing with shelving EQ is sufficient for speech. |

## Feature Dependencies

```
Text-level pause injection --> Model generates natural pauses (no dependency on post-FX)
Emotion tags --> Model generates pitch variation (no dependency on post-FX)
Reference audio quality --> Model replicates breathing, vocal quality (upstream of everything)

Soft saturation --> before compression (saturation generates harmonics that compression then controls)
Compression --> before additive EQ (prevents EQ boosts from triggering compressor)
Additive EQ --> after compression (character shaping without affecting dynamics)
Room convolution --> after EQ (applies room character to the shaped signal)
Limiter --> last in chain (safety net, prevents clipping)

PyWorld analysis --> independent of all post-FX (diagnostic tool)
```

## MVP Recommendation

Prioritize (highest impact per effort):
1. **Text-level pause injection** -- zero processing cost, biggest perceptual improvement
2. **LowShelfFilter warmth** -- one line added to existing `_post_fx`, immediate warmth
3. **Compressor** -- one line, evens out dynamics for "polished" feel
4. **HighShelfFilter air** -- one line, adds breath detail and intimacy

Defer:
- **Room convolution:** Requires asset sourcing and creative A/B testing. Include in later phase.
- **Soft saturation:** Needs careful tuning. Include after the EQ/compression chain is stable.
- **PyWorld metrics:** Build early for measurement, but not user-facing. Can run in parallel.

## Sources

- [Icon Collective: Effects Chain Order](https://www.mixinglessons.com/shelving-filter/)
- [Sage Audio: Vocal Effect Chaining](https://www.sageaudio.com/articles/how-to-chain-vocal-effects)
- [Production Expert: Free Impulse Responses](https://www.production-expert.com/production-expert-1/free-impulse-responses-excellent-for-sound-design-and-post-production)
- [Amazon Polly: SSML Breath Feature](https://docs.aws.amazon.com/polly/latest/dg/breath-tag.html) (for context on why to skip)
- [Picovoice: Complete Guide to TTS](https://picovoice.ai/blog/complete-guide-to-text-to-speech/)
- [arXiv: Prosodic Parameter Manipulation in TTS](https://arxiv.org/abs/2409.12176)
