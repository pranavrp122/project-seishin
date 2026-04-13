# Research Summary: TTS Humanism (v2.0)

**Project:** Fish Speech S2-Pro -- TTS Humanism Milestone
**Domain:** Speech naturalness via engine-side modifications (no model retraining)
**Researched:** 2026-04-13
**Confidence:** MEDIUM-HIGH

## Executive Summary

Fish Speech S2-Pro already produces clean, intelligible speech with good emotion tagging via 15,000+ inline `[tag]` directives and a DualAR transformer trained on 10M+ hours. The v2.0 humanism milestone aims to close the remaining gap between "good TTS" and "sounds like a person talking" through three levers: text pre-processing (tag/punctuation injection), audio post-processing (EQ, compression, saturation), and timing manipulation (pause patterns, breathing cues). The existing stack is almost sufficient -- pedalboard (Spotify, C++/JUCE backend) is already installed and handles the entire post-FX chain, numpy covers custom DSP, and the only new dependency is pyworld for offline F0 analysis. No heavyweight NLP, no new ML models, no model retraining.

The strongest consensus across all four research files is the "less is more" principle. The single most dangerous risk is the uncanny valley amplification effect: partially-humanized speech that is close-but-not-quite sounds worse than obviously synthetic speech. Every researcher independently flagged this. The mitigation is strict: add one feature at a time, A/B test each against unmodified baseline, ship only features that beat baseline on 95%+ of diverse inputs, and give every feature a 0.0-1.0 intensity dial. The second major consensus is to work WITH the model rather than against it -- Fish Speech's DualAR transformer already handles prosody, pitch contours, and some breathing. Post-processing that fights learned prosody produces artifacts. Text-level manipulation (punctuation, inline tags) is universally preferred over audio-level waveform surgery because it lets the model generate natural output rather than patching synthetic output.

Three things should be explicitly skipped: filler word injection (misplaced fillers are worse than none -- confirmed by KTH research), breathing sound synthesis (no Python library produces convincing breaths; the model already generates breaths from reference audio), and rule-based pitch manipulation at the waveform level (fights the model's learned prosody, produces sing-song artifacts). These are anti-features, not deferred features.

## Key Findings

### Recommended Stack

The stack is minimal because pedalboard and numpy already handle nearly everything. One new dependency (pyworld) is needed only for offline analysis, not in the real-time audio path.

**Core technologies:**
- **pedalboard** (0.9.22, already installed): Full post-FX chain -- Compressor, LowShelfFilter, HighShelfFilter, PeakFilter, Convolution, Limiter. JUCE-backed C++, 300x faster than pySoX. Replaces the current single PeakFilter with a professional vocal chain.
- **numpy** (already installed): Asymmetric soft saturation (`tanh` with quadratic asymmetry term for even-harmonic warmth). Pedalboard's Distortion is too aggressive for speech.
- **pyworld** (0.3.5, NEW -- only new dep): F0 extraction for measuring pitch variation, detecting monotonic output, and validating prosody improvements. BSD-like license. Analysis only, not real-time.
- **Static IR assets** (1-2 WAV files): Short room impulse responses for pedalboard.Convolution at very low mix (0.03-0.05). Provides "not a vacuum" presence without audible reverb. Royalty-free from Voxengo or Airborne Sound.

**Explicitly rejected:** parselmouth (GPL contamination), pyroomacoustics (overkill), python-stretch/pyrubberband (unnecessary if we avoid waveform time-stretching), spaCy (too heavy for POS tagging -- only needed if content-word emphasis is pursued, which is P2).

### Expected Features

**Must have (table stakes -- absence sounds noticeably synthetic):**
- Dynamic pause injection at punctuation (600ms optimal universal; 2:1 period-to-comma ratio)
- Presence/warmth EQ chain (HPF 80Hz, low-shelf 250Hz, presence 3.5kHz, air 8-10kHz)
- Gentle compression (threshold -18 to -20dB, ratio 2.0-2.5:1, 10ms attack, 100ms release)
- De-essing (narrow PeakFilter cut at 6.5kHz, Q=3.0, -2dB)
- Speech rate variation via text-level `[slow]`/`[fast]` tags at strategic points

**Should have (differentiators -- cross the line from "good TTS" to "forgot it was a machine"):**
- Subtle saturation for analog warmth (asymmetric tanh, drive=0.2-0.3)
- Room tone via Convolution IR at very low mix
- Breathing cues via `[inhale]` tag injection (sparse: before 15+ word phrases only, 1 per 3-5 sentences max)
- Varied pause duration with Gaussian jitter (+/-15-20% randomization)
- Volume dynamics for asides/emphasis (`[low volume]`/`[volume up]` tags)
- Trailing-off at sentence ends (validate model already does this; enhance only if needed)

**Defer (v3+ or LoRA milestone):**
- Vocal fry / creaky voice (must come from model training, not post-processing)
- Micro-pitch jitter (high artifact risk for marginal perceptual gain)
- Lip smacks / mouth sounds (extremely sparse use case, high uncanny valley risk)
- Content-word emphasis via POS tagging (requires spaCy dependency, P2 at best)
- Real-time prosody prediction models (adds latency and a new failure mode)
- Filler words (anti-feature -- DO NOT BUILD)

### Architecture Approach

The pipeline has four clean domains with a strict ordering constraint: Text Domain (before token generation) -> Token Domain (generation parameters) -> Audio Domain (after DAC decode, before crossfade) -> Streaming Domain (crossfade and emit, unchanged). All humanism modifications happen in either the Text Domain or Audio Domain. The Streaming Domain (crossfader, HTTP chunked response) is not modified.

**Major components:**
1. **Text Preprocessor [NEW]** -- Analyzes chunks from `split_text_into_chunks()`, injects pause markers / inline tags / punctuation, generates per-chunk HumanismHints metadata. Located in `inference.py` between chunk splitting and the batch generation loop.
2. **Audio Post-Processor [EXPANDED]** -- Replaces the single PeakFilter `_post_fx` chain with: saturation -> compressor -> EQ (HPF, warmth, presence, de-ess, air) -> convolution room tone -> limiter. Located in `get_audio_segment()` in `__init__.py`. Also handles text-driven gain adjustment using hints.
3. **Silence/Breath Inserter [NEW, optional]** -- Inserts calibrated silence or breath cue audio at chunk boundaries in the `inference()` loop, BEFORE crossfade. Probability-based (not every boundary). Located between `get_audio_segment()` and crossfade/yield.

**Critical ordering rules:**
- All audio processing BEFORE crossfade (crossfade is the last audio operation)
- Saturation BEFORE compression (saturation adds harmonics, compression tames peaks)
- EQ AFTER compression (prevents boosted frequencies from over-triggering compressor)
- Breath/silence insertion AFTER post-fx, BEFORE crossfade
- No reverb on individual segments (tails bleed across crossfade boundaries)
- No time-stretching of sub-chunk partials (breaks grow-and-redecode sample tracking)

### Critical Pitfalls

1. **Uncanny valley amplification** -- Partially-humanized speech sounds creepier than clean synthetic speech. Mitigate: incremental feature addition, A/B test each feature independently against unmodified baseline, implement 0.0-1.0 intensity dials, start at 20-30% intensity.

2. **Fighting the model's learned prosody** -- The DualAR transformer already learned pitch contours, pause timing, and emphasis from 10M+ hours. Explicit post-processing that overrides these patterns produces "over-processed" output. Mitigate: measure baseline behavior BEFORE implementing anything, fill gaps rather than duplicate, prefer text-level guidance over audio-level surgery.

3. **Pause timing failures** -- Too long (>800ms feels like system crash), too short (rushed/breathless), wrong placement (mid-clause sounds broken). In streaming, intentional pauses are indistinguishable from buffer underruns. Mitigate: variable durations with Gaussian jitter, never exceed 1s for automated pauses, fill pauses with room tone (not dead silence) so listeners know audio is still active.

4. **Post-processing artifacts in streaming** -- IIR filter state resets per chunk create transients at chunk boundaries. Compressor pumping after pauses. EQ resonance on certain phonemes. Mitigate: short attack/release times, correct signal chain order, test in streaming pipeline from day one (not batch-then-port).

5. **Demo effect (cherry-picked success)** -- Features tuned on short demo sentences fail on long passages, questions, code-mixed text, or boring content. Mitigate: adversarial test corpus (fragments, 50+ word sentences, numbers, mixed-language), generate 100+ diverse utterances and listen to ALL of them, measure worst case not average.

## Implications for Roadmap

### Phase 0: Baseline Measurement
**Rationale:** Every researcher independently flagged "measure before you modify." Without quantitative baseline data on what the model already does (pause distribution, pitch variation, breath gaps, spectral characteristics), we cannot distinguish improvements from regressions. This phase costs half a day and prevents weeks of wasted work.
**Delivers:** F0 statistics, pause distribution histogram, spectral profile, reference recordings for A/B testing.
**Stack:** pyworld (F0 analysis), numpy (statistics).
**Avoids:** Pitfall 11 (fighting the model), Pitfall 6 (demo effect -- establishes regression test corpus).

### Phase 1: Post-FX Chain
**Rationale:** Highest impact-to-risk ratio. Modifying a single class attribute in `__init__.py` with zero risk to streaming. Immediate warmth/presence improvement audible on every utterance. No text manipulation, no pipeline changes. All four researchers agree this is the obvious first move.
**Delivers:** Professional vocal chain -- warmth, presence, air, compression, de-essing, subtle saturation, room tone, safety limiter.
**Addresses:** Presence/warmth EQ (table stakes), compression (table stakes), de-essing (table stakes), saturation (differentiator), room tone (differentiator).
**Stack:** pedalboard (expand `_post_fx`), numpy (saturation function), static IR WAV files.
**Avoids:** Pitfall 5 (post-processing artifacts -- correct chain order, gentle ratios, test in streaming).

### Phase 2: Text Preprocessor + Pause System
**Rationale:** Second highest impact. Creates the infrastructure (HumanismHints) that later phases consume. Text-only modifications have zero audio risk -- they guide the model's existing prosody capabilities rather than overriding them. Pause injection is the single most cited naturalness gap in TTS.
**Delivers:** Punctuation-aware pause injection, `[pause]`/`[short pause]` tag insertion, per-chunk metadata for downstream phases, Gaussian pause duration variance.
**Addresses:** Dynamic pause injection (table stakes), speech rate variation (table stakes), varied pause duration (differentiator).
**Stack:** Python stdlib `re`, numpy (Gaussian jitter).
**Avoids:** Pitfall 4 (pause timing -- variable durations, semantic-aware placement, room tone in pauses), Pitfall 2 (over-engineered prosody -- text-level guidance, not waveform manipulation).

### Phase 3: Breathing Cues + Volume Dynamics
**Rationale:** Depends on Phase 2's chunk boundary data and HumanismHints. Breathing and volume variation are the features that cross the line from "good TTS" to "forgot it was a machine." Must be sparse and probability-based. This phase carries moderate uncanny valley risk and needs careful A/B testing.
**Delivers:** `[inhale]` tag injection at phrase starts (probability-based), `[low volume]`/`[volume up]` tag injection for asides/emphasis, text-driven per-segment gain adjustment.
**Addresses:** Breathing injection (differentiator), volume dynamics (differentiator).
**Avoids:** Pitfall 3 (breathing overuse -- hard cap 1 per 3-5 sentences, clause boundaries only), Pitfall 1 (uncanny valley -- A/B test each sub-feature independently).

### Phase 4: Validation + Tuning
**Rationale:** All features are in place; this phase validates the whole stack works together in streaming, tunes intensity parameters, and builds the regression test suite. The "demo effect" pitfall demands this as an explicit phase, not an afterthought.
**Delivers:** Adversarial test corpus results, streaming-specific validation, parameter tuning, regression test baseline for future changes, documentation of skip rationale for deferred features.
**Addresses:** Trailing-off validation (verify model already handles it), vocal fry documentation (skip rationale for LoRA milestone).
**Avoids:** Pitfall 6 (demo effect -- test on 100+ diverse utterances), Pitfall 8 (streaming breakage -- validate every feature in chunked pipeline), Pitfall 7 (consistency collapse -- fixed seed per request, test phoneme coverage).

### Phase Ordering Rationale

- **Phase 0 before everything** because Pitfall 11 (fighting the model) is the most insidious risk. Without baseline data, every subsequent decision is guesswork.
- **Phase 1 before Phase 2** because post-FX is pure audio with no pipeline dependencies. It produces an immediate quality improvement that makes subsequent A/B tests more meaningful (comparing "enhanced + pauses" vs "enhanced baseline" rather than "enhanced + pauses" vs "raw baseline").
- **Phase 2 before Phase 3** because the text preprocessor and HumanismHints infrastructure is consumed by breathing and volume dynamics. Building Phase 3 without the Phase 2 infrastructure would require throwaway code.
- **Phase 4 as explicit final phase** because the demo effect pitfall demands systematic validation. Treating validation as a separate phase ensures it gets allocated time rather than squeezed into the end of Phase 3.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Post-FX):** Convolution room tone needs A/B testing -- STACK.md recommends it but PITFALLS.md warns about room tone mismatch. May need to test multiple IRs or skip convolution entirely. Also: compressor-before-EQ vs EQ-before-compressor ordering disagreement between FEATURES.md and ARCHITECTURE.md -- needs empirical resolution.
- **Phase 3 (Breathing + Volume):** Highest uncanny valley risk. The STACK.md researcher recommends skipping breath synthesis entirely (model handles it), while FEATURES.md recommends `[inhale]` tag injection. Resolution: try tag-based breathing first (leverages model), fall back to skip if model response to `[inhale]` is inadequate.

Phases with standard patterns (skip research-phase):
- **Phase 0 (Baseline):** Straightforward pyworld F0 extraction + numpy statistics. Well-documented pattern.
- **Phase 2 (Text Preprocessor):** Punctuation injection and pause markup are well-documented patterns with academic pause duration data available.
- **Phase 4 (Validation):** Standard A/B testing methodology, no novel research needed.

## Cross-Researcher Disagreements

Three areas where the four research files do not fully align:

1. **Signal chain order (compressor placement):** ARCHITECTURE.md puts pitch shift -> EQ -> compressor -> gain. FEATURES.md puts compressor -> EQ (compression before EQ). STACK.md puts compressor -> EQ -> convolution -> limiter. PITFALLS.md says "EQ first, then compression." **Resolution:** The ARCHITECTURE.md order (EQ before compressor) is the safer choice for TTS because it lets the compressor manage dynamics of the shaped signal. FEATURES.md's "compression before EQ" argument (prevent boosted frequencies from over-triggering) is valid for aggressive EQ but moot with gentle 1-2dB boosts. Go with: saturation -> EQ -> compressor -> convolution -> limiter.

2. **Breathing approach:** STACK.md says skip breathing entirely (model handles it from reference audio). FEATURES.md says inject `[inhale]` tags before long phrases. ARCHITECTURE.md maps out audio-level breath sample mixing. PITFALLS.md warns about uncanny synthetic breaths. **Resolution:** Try `[inhale]` tag injection first (zero audio risk, leverages model). If model produces good breaths from the tag, ship it. If not, skip breathing entirely. Do NOT pursue audio-level breath sample mixing.

3. **Room tone / Convolution:** STACK.md recommends Convolution IR at 0.03-0.05 mix. FEATURES.md recommends pink noise at -60dB. PITFALLS.md warns about room tone mismatch. ARCHITECTURE.md says no reverb on individual segments. **Resolution:** Start with NO room tone. Add Convolution IR only if A/B testing shows clear improvement. The "not a vacuum" problem may be solved by compression alone (raises quiet passages).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | pedalboard verified in codebase, pyworld is standard in TTS research, all alternatives evaluated with clear rationale |
| Features | MEDIUM-HIGH | Table stakes well-supported by academic pause research and industry practice. Differentiator impact less certain -- needs A/B validation. Anti-features strongly supported. |
| Architecture | HIGH | Based on direct codebase analysis of every integration point. Pipeline constraints verified against actual code. |
| Pitfalls | MEDIUM-HIGH | Uncanny valley and demo effect are well-documented across industry. Streaming-specific pitfalls need Fish Speech-specific testing. Pause duration thresholds are approximations. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **`[inhale]` tag effectiveness:** S2-Pro supports 15,000+ tags but whether `[inhale]` produces convincing breaths has not been tested. This gates the entire Phase 3 breathing approach. Test early in Phase 0 baseline work.
- **Compressor state across chunks:** The _post_fx Pedalboard is re-invoked per segment. Whether pedalboard carries IIR filter state across calls or resets needs empirical testing. If it resets, short attack/release times mitigate but do not eliminate the transient.
- **`[slow]`/`[fast]` tag effectiveness:** These tags are assumed to work based on S2-Pro's free-form tag system. If the model does not respond meaningfully, speech rate variation falls back to chunk-size manipulation (crude but safe).
- **Room tone necessity:** Whether the DAC codec output actually sounds "sterile" in practice, or whether compression + EQ already provides sufficient warmth, is unknown. May be a non-issue.
- **Vocal fry from reference audio:** The 17.27s reference clip's vocal characteristics have not been analyzed. If it lacks vocal fry, the model will not produce it -- this is fine for v2.0 but should be documented for the LoRA milestone.

## Sources

### Primary (HIGH confidence)
- Fish Speech S2-Pro codebase: direct analysis of `inference_engine/__init__.py`, `models/text2semantic/inference.py`, `inference_engine/crossfader.py`
- [Spotify Pedalboard v0.9.22 API](https://spotify.github.io/pedalboard/reference/pedalboard.html) -- full effects list confirmed
- [Fish Audio S2 tag documentation](https://fish.audio/s2/) -- 15,000+ inline tags including `[pause]`, `[inhale]`, `[emphasis]`
- [PyWorld v0.3.5](https://pypi.org/project/pyworld/) -- BSD-like license, F0/SP/AP extraction
- [Stanford CCRMA: Soft Clipping](https://ccrma.stanford.edu/~jos/pasp/Soft_Clipping.html) -- tanh waveshaping theory
- [Frontiers in Psychology: Pause Duration & Naturalness](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2022.778018/full) -- 600ms optimal, 2:1 ratio

### Secondary (MEDIUM confidence)
- [Szekely 2019: How to Train Your Fillers (KTH)](https://www.speech.kth.se/tts-demos/ssw19/szekely2019how.pdf) -- misplaced fillers worse than none
- [Amazon Polly SSML Breath Feature](https://aws.amazon.com/blogs/machine-learning/amazon-polly-releases-new-ssml-breath-feature/) -- industry breath insertion reference
- [Sesame: Crossing the Uncanny Valley of Voice](https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice) -- uncanny valley confirmation
- [ScienceDirect: Non-monotonic uncanniness function](https://www.sciencedirect.com/science/article/pii/S2451958824000630) -- vocal uncanny valley research
- [Raitio et al. 2013: HMM-based Synthesis of Creaky Voice](https://www.isca-archive.org/interspeech_2013/raitio13b_interspeech.html) -- vocal fry synthesis is hard
- Multiple practitioner sources on demo-to-production quality gap (Talkdesk, Medium, Channel.tel)

### Tertiary (LOW confidence, needs validation)
- Campione & Veronis pause categories -- primary source is older, cited indirectly
- `[creaky]` / `[vocal fry]` tag response in S2-Pro -- untested
- Micro-pitch jitter implementation -- extrapolated from voice analysis literature, no direct TTS post-processing reference

---
*Research completed: 2026-04-13*
*Ready for roadmap: yes*
