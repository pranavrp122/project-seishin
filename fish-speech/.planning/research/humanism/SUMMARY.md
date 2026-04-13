# Research Summary: TTS Humanism & Naturalness

**Domain:** Speech post-processing and naturalness enhancement for neural TTS
**Researched:** 2026-04-13
**Overall confidence:** HIGH

## Executive Summary

Making neural TTS sound human requires attacking six dimensions: tonal warmth, dynamic control, pause timing, pitch variation, spatial presence, and breath. The good news is that the existing Fish Speech codebase already has the primary tool (pedalboard by Spotify) and the model itself handles the hardest parts (prosody from emotion tags, breath from reference audio).

The research found that the professional audio engineering approach to vocal naturalness -- a signal chain of saturation, compression, EQ, and subtle room convolution -- maps cleanly onto available Python tools. Pedalboard provides 5 of the 6 needed effects natively. The only custom DSP needed is a 5-line asymmetric soft saturator in numpy for even-harmonic warmth (standard technique from analog modeling).

One new dependency is recommended: `pyworld` (v0.3.5) for measuring pitch variation and pause timing in generated output. This is an analysis tool, not in the real-time path -- it provides objective metrics to validate that humanism improvements are actually working.

Breathing sound synthesis was investigated and explicitly rejected. No Python library produces convincing breath sounds. The model already generates natural breathing from its training data and reference audio. Synthetic breath injection would degrade quality.

## Key Findings

**Stack:** Expand existing pedalboard chain (Compressor + LowShelfFilter + PeakFilter + HighShelfFilter + Convolution + Limiter), add numpy soft saturation, add pyworld for analysis. One new pip dependency total.

**Architecture:** Post-FX chain runs after DAC decoder, before streaming output. Text-level punctuation injection happens before model inference. PyWorld analysis is offline/diagnostic only.

**Critical pitfall:** Over-processing. Every effect adds latency and risks making speech sound processed rather than natural. Start with bypass-level parameters and increase gradually. A/B test against unprocessed output at every step.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Text-level pause injection** - Highest impact, zero processing cost
   - Addresses: Rhythm, breathing space, natural pacing
   - Avoids: Over-processing pitfall (changes happen before generation)
   - Rationale: Fish Speech already responds to punctuation. Injecting commas, semicolons, and ellipses at clause boundaries is the single most impactful change with zero audio processing overhead.

2. **Post-FX chain expansion** - High impact, low risk
   - Addresses: Warmth, presence, dynamic control
   - Avoids: Dependency bloat (pedalboard already installed)
   - Rationale: Expanding `_post_fx` from 1 effect to 6 is a config change, not an architecture change. Start with gentle parameters, tune by ear.

3. **Soft saturation** - Medium impact, novel code
   - Addresses: Analog warmth, "alive" quality
   - Avoids: Aggressive distortion (asymmetric tanh, not hard clipping)
   - Rationale: 5-line numpy function, but needs careful tuning. Too much drive sounds processed; too little is inaudible.

4. **Room tone convolution** - Medium impact, requires assets
   - Addresses: "Speaking in a room" presence vs. "speaking in a void"
   - Avoids: Reverb (Convolution with short dry IR, not algorithmic reverb)
   - Rationale: Requires sourcing and testing impulse response WAV files. Pedalboard Convolution handles the DSP, but the creative choice of IR matters.

5. **Prosody measurement system** - Diagnostic, informs tuning
   - Addresses: Objective validation of improvements
   - Avoids: Subjective-only evaluation
   - Rationale: PyWorld F0 analysis provides measurable metrics (pitch std dev, pause count/duration). Build this early to measure progress, but it's not user-facing.

**Phase ordering rationale:**
- Text-level changes (phase 1) produce the biggest improvement with no processing cost and no risk of degradation
- Post-FX chain (phase 2-3) is incremental and tunable -- each effect can be individually bypassed
- Room tone (phase 4) requires asset sourcing as a prerequisite
- Measurement (phase 5) is diagnostic tooling that can be built in parallel with any phase

**Research flags for phases:**
- Phase 1: Standard patterns, unlikely to need deeper research. Fish Speech punctuation handling is documented.
- Phase 2: Standard patterns. Pedalboard API is well-documented.
- Phase 3: May need deeper research on drive/asymmetry tuning ranges for speech specifically (most resources target music)
- Phase 4: Needs creative asset selection (which room IR sounds best). Budget time for A/B listening tests.
- Phase 5: Standard F0 analysis. PyWorld API is simple.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Post-FX chain (pedalboard) | HIGH | Already in codebase, API verified, professional vocal chain ordering well-documented |
| Soft saturation (numpy tanh) | HIGH | Standard DSP technique, verified at Stanford CCRMA, musicdsp.org, KVR forums |
| Pause injection (text-level) | HIGH | Fish Speech already responds to punctuation; confirmed in model behavior |
| Room tone (Convolution + IR) | MEDIUM | Pedalboard Convolution verified; IR selection is creative/subjective |
| Prosody measurement (pyworld) | HIGH | Standard tool in TTS research, v0.3.5 released Jan 2025 |
| Breathing (skip decision) | HIGH | No convincing implementation exists; model handles it natively |

## Gaps to Address

- **Saturation tuning ranges for speech:** Most soft-clipping literature targets music. Need empirical testing to find drive/asymmetry sweet spot for 44.1kHz speech at typical TTS loudness levels.
- **Room IR selection:** Need to download and A/B test several impulse responses to find ones that add presence without coloring the voice. This is a subjective/creative decision, not a technical one.
- **Interaction between effects:** Compressor before saturation vs. after saturation changes the character significantly. The recommended order (compressor first) is based on vocal chain best practices, but may need adjustment for TTS-specific characteristics.
- **Per-chunk vs. per-utterance processing:** The current `_post_fx` runs per-chunk. Some effects (compression) maintain state across calls. Need to verify pedalboard handles stateful processing correctly when called repeatedly on streaming chunks.
