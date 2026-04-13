# Domain Pitfalls: TTS Naturalness / Humanism

**Domain:** Making Fish Speech S2-Pro sound more human-like through TTS engine modifications
**Researched:** 2026-04-13
**Milestone:** v2.0 TTS Humanism
**Overall confidence:** MEDIUM-HIGH (synthesized from industry sources, practitioner reports, and academic literature)

---

## Critical Pitfalls

Mistakes that make speech sound actively *worse* than the current baseline, or that require fundamental rework.

---

### Pitfall 1: The Uncanny Valley Amplification Effect

**What goes wrong:** Adding "human" features (breathing, fillers, micro-pauses, vocal fry) to speech that is already reasonably good pushes it *into* the uncanny valley rather than *past* it. When a voice gets close to sounding real, every tiny mistake becomes more noticeable -- a pause that is half a second too long, a breath in the wrong place, or a filler word with slightly wrong timing. The result is that partially-humanized speech sounds creepier than the original "clean" robotic output.

This is the single most dangerous pitfall for this milestone. The current Fish Speech output is clean and intelligible with good emotion tagging. Adding naturalness features risks landing in "almost human but off" territory, which listeners find more unsettling than obviously synthetic speech.

**Why it happens:** Human perception of voice naturalness is nonlinear. Research confirms a non-monotonic uncanniness function when plotted against human-likeness -- the uncanny valley exists for audio just as it does for visual human likenesses. Partial naturalness features signal "this should be human" to the listener's brain, which then scrutinizes every remaining synthetic artifact 10x harder than it would in clearly-synthetic speech.

**Consequences:** Users who previously tolerated the output now find it unsettling. Trust drops. The "improvement" is perceived as a regression.

**Warning signs:**
- A/B testers describe the new output as "creepy," "trying too hard," or "unsettling" even though they cannot pinpoint what is wrong
- Individual features (breathing, pauses) sound fine in isolation but feel wrong together
- The enhanced output tests worse in MOS (Mean Opinion Score) than the original despite having objectively more human-like characteristics

**Prevention:**
1. **Always A/B test against the unmodified baseline** on blind listeners before shipping any naturalness feature. If a feature does not beat baseline in listener preference, do not ship it -- even if it is technically more "human-like."
2. **Add features incrementally.** One feature at a time, tested. Never stack breathing + fillers + vocal fry + micro-pauses simultaneously.
3. **Implement a bypass/mix knob.** Every naturalness feature should have a 0.0-1.0 intensity parameter so it can be dialed back or disabled without code changes.
4. **Start subtle.** Begin with features at 20-30% of their "realistic" intensity and increase only if testing confirms improvement.

**Phase mapping:** Applies to ALL phases. Must be the governing principle throughout the milestone.

---

### Pitfall 2: Over-Engineered Prosody ("The Sing-Song Problem")

**What goes wrong:** Explicitly manipulating pitch contours, emphasis patterns, or speech rate variation produces a new kind of unnaturalness -- speech that sounds "sing-song," over-modulated, or like a bad radio DJ. This is the mirror image of monotone speech: instead of too-flat pitch, you get exaggerated, rhythmic pitch patterns that no human actually produces in conversation.

The quality impact of pitch control depends on balancing customization with natural speech patterns. Poorly implemented pitch control results in speech that sounds exaggerated or inconsistent, and overly rigid adjustments sound robotic in a new way.

**Why it happens:**
- Rule-based prosody ("raise pitch 20% on emphasized words, lower 15% at sentence end") produces mechanical patterns that repeat predictably. Humans vary these patterns every time.
- Training prosody models separately from the acoustic model degrades overall quality. Research confirms that "while this enables fully controllable prosody, the quality of the synthesized speech is somewhat worse, compared to jointly trained seq2seq neural TTS systems."
- Overcorrecting for flat intonation by naively adding pitch/rate variation without context awareness produces patterns no human would use.

**Consequences:** Speech sounds like a GPS navigation voice or a sing-along -- technically varying in pitch but in a way that immediately signals "machine." Users notice and dislike it even if they cannot articulate why.

**Warning signs:**
- Pitch contour looks periodic or symmetric when plotted (real speech pitch is messy and asymmetric)
- The same emphasis pattern repeats across unrelated sentences
- Listeners describe the voice as "enthusiastic in a fake way" or "like it is reading to a child"
- The voice sounds better on short demo sentences than on paragraphs of conversational text

**Prevention:**
1. **Do not implement rule-based pitch manipulation.** Fish Speech's DualAR transformer already produces learned prosody from training data. Adding explicit pitch curve modifications on top will fight the model's own prosody predictions and produce artifacts.
2. **If modifying prosody, work at the token/embedding level** -- not the waveform level. Adjust prosodic embedding inputs to the model rather than post-processing the output audio pitch.
3. **Use the model's own capabilities.** Choose reference audio that naturally exhibits the desired prosodic style. The reference audio's 372 semantic tokens already encode prosodic patterns that the model clones.
4. **Test on boring sentences.** Prosody enhancements that sound great on "The quick brown fox jumps over the lazy dog!" will fall apart on "Please confirm your appointment for Tuesday at 3:00 PM."

**Phase mapping:** Prosody enhancement phase. This pitfall gates whether explicit prosody manipulation should be attempted at all vs. relying on reference audio selection and training data quality.

---

### Pitfall 3: Filler Word and Breathing Overuse

**What goes wrong:** Injecting "um," "uh," breaths, and hesitation sounds to make speech sound conversational crosses a line from "sounds human" to "sounds like the speaker has a speech impediment" or "sounds drunk." A telemarketing study found success rates dropped in proportion to filler word use, especially after use exceeded 1.3% of total words. Overuse of filler words is clinically associated with stuttering.

TTS models like XTTS v2 already suffer from hallucinating unwanted breathing sounds and vocalization artifacts ("aah," "yee," gibberish) -- especially at utterance ends. Deliberately adding more breath/filler tokens risks amplifying this existing problem.

**Why it happens:**
- Developers test fillers on individual sentences where one "um" sounds natural, then apply the same rate to all output. In longer passages, the cumulative effect is overwhelming.
- Breath sounds are acoustically complex (broadband noise with specific spectral shape and duration). Synthetic breaths that are even slightly wrong in timing, spectral shape, or loudness immediately sound artificial.
- The model may already produce some natural hesitation and breathing from its training data. Adding explicit fillers on top doubles the frequency.

**Consequences:** Voice sounds impaired, hesitant, or nervous. Listeners focus on the fillers rather than the content. In professional/formal contexts (narration, customer service), fillers actively damage perceived quality.

**Warning signs:**
- More than 1-2 fillers per 100 words of output
- Breath sounds placed at positions where no human would breathe (mid-word, mid-clause before a short word)
- Listeners describe the voice as "nervous" or "stuttering"
- Fillers appear at mechanically regular intervals rather than at natural decision points

**Prevention:**
1. **Audit what the model already does.** Before adding any filler/breath injection, analyze the current output's existing breath-like pauses and hesitation markers. The model may already produce enough.
2. **Context-appropriate fillers only.** Fillers belong in conversational speech, NOT in narration, reading, or formal announcements. Implement different profiles (conversational vs. narrated) and default to the conservative one.
3. **Cap filler density.** Hard maximum of 1 filler per 50-80 words. Never place two fillers within 5 seconds of each other.
4. **Breath sounds at clause boundaries only.** Breathing only at positions where a human would run out of air: after long clauses (15+ words), at sentence boundaries, or before a new thought. Never mid-clause.
5. **Synthetic breath quality matters enormously.** If the breath sound is not nearly indistinguishable from a real breath, do not include it. A bad synthetic breath is far worse than no breath at all.

**Phase mapping:** Breathing/filler evaluation phase. This pitfall strongly argues for the "evaluate and document skip rationale" path over the "implement" path, unless the synthetic breath quality is exceptional.

---

### Pitfall 4: Pause Timing Failures

**What goes wrong:** Three distinct failure modes:

**Too long:** Pauses over 800ms-1s feel like the system has crashed or is buffering. Users check their connection. In streaming contexts, long pauses are indistinguishable from buffer underruns.

**Too short:** No pause between sentences or after punctuation creates rushed, breathless speech. Listeners cannot process the content and feel stressed.

**Wrong placement:** Pausing mid-clause in grammatically incorrect positions ("I want to / go to the store" with a 300ms pause at /) sounds broken. Pausing before trivial words ("I went to the / the store") sounds like a stutter.

**Why it happens:**
- Punctuation-based rules are too coarse. A comma in "red, blue, and green" needs a different pause than a comma in "However, the situation changed." Same punctuation, different semantic weight.
- Fixed-duration pauses sound mechanical. Humans vary pause duration based on what comes next -- longer before complex ideas, shorter before simple continuations.
- In streaming/chunked generation, natural pauses can coincide with chunk boundaries, making it impossible for the listener to distinguish intentional pauses from processing delays.

**Consequences:** Short pauses make speech feel rushed and robotic (a new kind of robotic). Long pauses break immersion and trigger "is it working?" anxiety in interactive contexts. Wrong-place pauses sound like speech errors.

**Warning signs:**
- All pauses are the same duration regardless of context
- Pauses appear at every comma with no variation
- Streaming users report "the voice keeps stopping and starting"
- Speech sounds like a list being read even when the content is conversational

**Prevention:**
1. **Variable pause durations.** Commas: 150-350ms (vary based on clause length). Periods: 300-600ms. Paragraph breaks: 500-900ms. Never exceed 1s for any automated pause.
2. **Semantic-aware placement.** Pause length should correlate with the complexity of what follows, not just punctuation type. Longer pauses before new topics, shorter pauses in lists.
3. **Distinguish streaming pauses from intentional pauses.** In streaming mode, intentional pauses should be filled with a tiny amount of room tone (not dead silence) so the listener knows audio is still active. Dead silence = "connection dropped" in the listener's mind.
4. **Add jitter.** Every pause should have +/-15-20% random variation. Perfectly regular pause timing (exactly 300ms every time) is a dead giveaway of synthesis.

**Phase mapping:** Pause/delay injection phase. Core implementation concern.

---

## Moderate Pitfalls

---

### Pitfall 5: Post-Processing Artifact Introduction

**What goes wrong:** Applying audio post-processing (EQ warmth, compression, subtle reverb, room tone) to add "presence" and "warmth" to the output introduces artifacts that were not in the original synthesis. These include:

- **Compression pumping:** Compressor gain reduction creates audible volume swelling, especially after pauses. The loudest part of the signal triggers compression on the entire signal, including reverb tails.
- **EQ resonance:** Boosting frequencies for "warmth" (200-400Hz) or "presence" (2-5kHz) can create resonant peaks that make certain phonemes ring unnaturally.
- **Reverb smearing:** Room reverb applied to short utterances smears consonant transients, reducing intelligibility. The reverb tail from one phrase bleeds into the next.
- **Filter state discontinuities in streaming:** IIR filters (which most EQ and compression implementations use) have internal state. The existing `_post_fx` PeakFilter (3500Hz, +1.5dB, Q=0.7) already applied per-chunk creates a transient at the start of each chunk when the filter state resets to zero.

**Why it happens:** Post-processing is designed for recorded audio, not synthesized audio. Synthesized audio has different spectral characteristics (typically cleaner, with less natural variation in level) that make compressors and EQs behave differently than expected. In streaming mode, per-chunk processing compounds the problem.

**Warning signs:**
- Volume "breathes" (audible gain changes) after pauses or quiet passages
- Sibilants ("s," "sh") become harsh or sharp after EQ
- Consonant clarity drops (words become "mushy") after reverb
- Clicks or pops at chunk boundaries are worse with post-processing than without

**Prevention:**
1. **Signal chain order matters.** EQ first (cut problem frequencies, boost gently), then compression, then reverb. Never compress after reverb -- it creates the swelling artifact.
2. **Subtract, do not add.** Cut harsh frequencies rather than boosting warm ones. A high-shelf reduction at 6-8kHz does more for "warmth" than a low-shelf boost at 200Hz.
3. **Gentle ratios.** Compression ratio no higher than 2:1 for TTS warmth. Attack > 10ms to preserve consonant transients. Release > 100ms to avoid pumping.
4. **Carry filter state across chunks.** For streaming, maintain IIR filter state between chunks rather than re-initializing. This eliminates the per-chunk transient. Alternatively, apply post-processing after chunk stitching (for non-streaming) or use FIR filters (linear phase, no state dependency).
5. **A/B test raw vs. processed on diverse content.** Post-processing that sounds great on a demo sentence may hurt intelligibility on rapid dialogue or whispered speech.

**Phase mapping:** Post-processing for warmth/presence phase. Must be validated against streaming pipeline.

---

### Pitfall 6: The "Demo Effect" (Cherry-Picked Success)

**What goes wrong:** Naturalness techniques are tuned and demonstrated on specific sentences that showcase the feature well. In production with arbitrary input text, the same techniques produce wildly variable quality. Specific failure patterns:

- **Techniques tuned on short sentences fail on long passages.** Models degrade with longer inputs -- studies show error rates exceeding 25-32% on longer content for some models.
- **Techniques tuned on declarative text fail on questions, commands, exclamations, or code-mixed text.** Each sentence type needs different prosodic treatment.
- **Techniques tuned on clean input fail on real-world text.** Abbreviations, numbers, URLs, code snippets, mixed-language text, and unusual punctuation all break naturalness features in unexpected ways.
- **Performance that is great in batch mode degrades in streaming.** Non-streaming TTS results can be significantly better than streaming results, especially in coherence.

Real practitioners report: "What works in a demo often does not work in real life." After 8+ years of deploying AI for voice, the gap between demo quality and production quality remains one of the top industry challenges.

**Why it happens:** Developers naturally test with sentences that sound good and then ship. The distribution of real-world input text is far broader and messier than any test set. Additionally, latency that is invisible in a demo compounds in production under load.

**Warning signs:**
- MOS scores are high on your test set but user complaints are frequent
- The voice sounds great on the first 3 sentences of any text but degrades on subsequent ones
- Quality varies dramatically between different types of content (narrative vs. dialogue vs. technical)
- Streaming quality is noticeably worse than batch-generated quality for the same text

**Prevention:**
1. **Test on adversarial inputs.** Build a test corpus that includes: sentence fragments, very long sentences (50+ words), questions, exclamations, numbers and dates, mixed-language text, text with unusual punctuation, and boring/repetitive content.
2. **Test on quantity.** Generate 100+ diverse utterances and listen to all of them, not just the best 5. Track the failure rate, not the best case.
3. **Test in streaming mode specifically.** Every feature must be validated in the actual streaming pipeline (chunked generation, crossfaded output) not just in single-shot batch mode.
4. **Measure the worst case, not the average.** A feature that makes 80% of utterances better but makes 20% terrible is worse than no feature at all. Users remember the bad experiences.
5. **Regression testing against baseline.** For every new feature, re-run the full test corpus and compare to the pre-feature baseline. Never let a "naturalness improvement" regress quality on any significant subset of inputs.

**Phase mapping:** Applies to ALL phases. Must be baked into the testing methodology from the start.

---

### Pitfall 7: Consistency Collapse Across Utterances

**What goes wrong:** Naturalness features sound good on some sentences but terrible on others within the same generation. The voice shifts tone, pronunciation, rhythm, or character unpredictably across utterances. This is distinct from prosody drift (which is gradual) -- this is sudden, per-sentence quality variance.

Studies confirm this is a systemic TTS problem: "A TTS system that shifts tone, pronunciation, or rhythm unpredictably can confuse and frustrate users." Even among leading commercial models, some are inconsistent in naturalness across different sentence types.

**Why it happens:**
- Neural TTS models produce non-deterministic output (sampling randomness). Temperature, top-p, and other sampling parameters create different realizations each time.
- Some phoneme combinations interact poorly with naturalness features. A breath injection that sounds fine before "I think" sounds terrible before "sss" or "fff" sounds.
- Naturalness features applied uniformly ignore sentence-level context. Not every sentence in a passage should have the same level of informality, hesitation, or expression.

**Consequences:** The listener's attention keeps getting pulled to quality variations rather than content. Even if the average quality is higher, the variance itself is perceived as a problem.

**Warning signs:**
- Generating the same text three times produces noticeably different naturalness quality each time
- Some phoneme/word combinations consistently produce worse output
- Naturalness features work well on English but produce artifacts on other languages or code-switched text

**Prevention:**
1. **Reduce sampling randomness.** Use lower temperature (0.5-0.7 instead of 1.0) and tighter top-p for naturalness features. Consistency is more important than variety.
2. **Test on phoneme coverage.** Build a test corpus that covers all common phoneme combinations, especially challenging ones (sibilants, plosives, nasals before/after pauses and breaths).
3. **Per-sentence naturalness profiling.** Analyze each sentence before applying features. Short functional sentences ("OK." "Got it." "Sure.") need different treatment than long expressive ones.
4. **Fixed seed per request.** Use a consistent random seed across all chunks/utterances within a single generation request to reduce inter-utterance variance.

**Phase mapping:** All phases, but especially critical for pause injection and prosody enhancement phases.

---

### Pitfall 8: Streaming-Specific Naturalness Breakage

**What goes wrong:** Naturalness techniques that work in batch (full-text) generation fail when audio is chunked and streamed. Specific failure modes:

- **Pauses at chunk boundaries are doubled.** If the text is split at a period, the model generates utterance-final prosody (natural pause) AND the streaming system adds its own pause. The result is an unnaturally long gap.
- **Breathing sounds get cut in half.** A breath sound that spans a chunk boundary is split into two halves by the crossfade, producing a bizarre truncated gasp.
- **Prosody resets at chunk starts.** Each chunk starts with "beginning of utterance" energy regardless of what came before, creating a sawtooth energy pattern.
- **Post-processing artifacts compound.** The existing PeakFilter transient + crossfade region + prosody reset all pile up at the same chunk boundary point.

**Why it happens:** Naturalness features are typically designed and tested with full-text context available. Chunked generation loses future context, and each chunk is independently processed by the model. The crossfade/overlap system masks waveform discontinuities but cannot fix prosodic or semantic discontinuities.

**Warning signs:**
- Enhanced audio sounds natural in batch mode but choppy or inconsistent in streaming mode
- Pauses and breaths cluster at chunk boundaries rather than being distributed naturally
- The energy/volume envelope has visible discontinuities at chunk boundaries even after crossfading

**Prevention:**
1. **Design for streaming first.** Every naturalness feature should be designed and tested in the streaming pipeline from day one. Do not develop in batch mode and port to streaming later.
2. **Pause injection must account for chunk boundaries.** If a chunk naturally ends with falling prosody, do not add additional pause. If a chunk boundary coincides with a comma, the comma pause must be generated by the model (in the chunk's output), not injected as silence between chunks.
3. **Breathing and fillers must not span chunk boundaries.** If injecting breath/filler tokens, ensure they are fully contained within a single chunk with a safety margin of at least 100ms from the chunk edge.
4. **Test naturalness in streaming at production chunk sizes.** The project's target chunk sizes (200-300 bytes of text) should be the test environment, not longer batch inputs.

**Phase mapping:** All phases. The streaming pipeline from milestone v1.0 is the operating constraint for every naturalness feature.

---

## Minor Pitfalls

---

### Pitfall 9: Vocal Fry / Creaky Voice Implementation Failure

**What goes wrong:** Vocal fry (the low-frequency creaky sound at the end of phrases) is one of the most recognizable human vocal characteristics and also one of the hardest to synthesize. The creaky excitation displays different acoustic characteristics than modal excitations and is "not suitably modelled by standard vocoders." When implemented poorly, it sounds like digital distortion, audio dropout, or the speaker clearing their throat.

**Prevention:**
1. Do not attempt to add vocal fry through post-processing or waveform manipulation. It must come from the model's learned behavior or reference audio.
2. If the reference audio clip (17.27s) does not exhibit vocal fry, the model will not produce it. Choose or supplement reference audio that naturally includes the desired vocal quality.
3. If vocal fry is desired, fine-tuning (LoRA) on data with natural vocal fry is far more reliable than any post-processing approach. This is out of scope for this milestone but should be documented for the LoRA milestone.

**Phase mapping:** Breathing/filler evaluation phase (to document skip rationale).

---

### Pitfall 10: Room Tone / Ambience Mismatch

**What goes wrong:** Adding "room tone" (subtle background noise that simulates a physical space) to create presence backfires when the room tone does not match the voice's acoustic properties. If the synthesized voice sounds like it was recorded in a studio (dry, no reverb) but the room tone suggests a living room (subtle reverb, wider stereo), the mismatch is jarring. Worse, room tone added to streamed audio must be continuous -- any gap in room tone at chunk boundaries signals the synthesis.

**Prevention:**
1. Room tone must be spectrally matched to the voice's own reverb characteristics. Analyze the reference audio clip's room tone and match that.
2. Room tone must be continuous across chunks -- it should be generated independently of the speech chunks and mixed in at the final output stage.
3. Start with no room tone (dry output) and only add it if testing shows clear improvement. The DAC codec already produces clean output; adding noise rarely helps.

**Phase mapping:** Post-processing for warmth/presence phase.

---

### Pitfall 11: Naturalness Features Fighting the Model

**What goes wrong:** Fish Speech S2-Pro's DualAR transformer was trained on 10M+ hours of diverse speech data. It has already learned prosodic patterns, pause timing, emphasis, and speaking rate variation from its training data. Adding explicit naturalness features on top of what the model already produces creates conflicts -- explicit pause injection fights the model's learned pauses, explicit pitch modification fights the model's learned pitch contours, and post-processing warmth fights the DAC codec's learned spectral balance.

The result is a voice that sounds "over-processed" -- like a photo with too many Instagram filters. Each individual filter might improve something, but stacked together they produce an unnatural result.

**Prevention:**
1. **Measure the baseline first.** Before implementing any naturalness feature, quantitatively measure what the model already does: its pause distribution, pitch variation range, breath-like gaps, and spectral characteristics.
2. **Fill gaps, do not duplicate.** Only add features that address measurable deficiencies in the current output. If the model already pauses naturally at periods, do not add pause injection at periods.
3. **Work with the model, not against it.** Use text preprocessing (adding punctuation, adjusting phrasing) and reference audio selection to guide the model's existing capabilities rather than overriding its output with post-processing.

**Phase mapping:** Research/analysis phase should precede any implementation.

---

## Lessons from ElevenLabs and PlayHT

### What ElevenLabs Got Wrong (and Fixed)

1. **Stability/Similarity slider overexposure:** Early versions exposed raw model parameters (stability, similarity boost) to users. Setting similarity too high on low-quality source audio reproduced noise and artifacts. Setting stability too low produced wildly random, sometimes incoherent output. Fix: introduced sensible defaults, added Speaker Boost for clarity, and added Style Exaggeration as a separate controlled parameter.

2. **Non-determinism without controls:** Early versions had no way to reduce inter-generation variance. Each generation of the same text could sound noticeably different. Fix: added speed control and more deterministic generation options.

3. **Long-form degradation:** Quality degraded on passages longer than ~500 words. Fix: improved text chunking, better context management across chunks.

4. **Background noise reproduction:** Voice clones faithfully reproduced background noise from source samples. Fix: recommended high-quality source audio, added noise reduction options.

**Lesson for Fish Speech:** The knob-per-feature approach (stability, similarity, style) creates combinatorial complexity. Sensible defaults that work for 90% of cases are better than maximum configurability.

### What PlayHT Got Wrong (and Fixed)

1. **Flat emotional delivery:** Early conversational models maintained natural dialogue flow but felt "flat with complex emotions." Fix: introduced emotion-specific models and prosody-aware generation.

2. **Long-form consistency:** Voice realism was good but "not always consistent," especially in long-form speech. Fix: improved context window management and consistency-focused training.

3. **Inflection on complex terms:** Natural inflection struggled with technical terms, proper nouns, and unusual words. Fix: improved pronunciation models and user-facing pronunciation customization.

**Lesson for Fish Speech:** Consistency across sentence types and content complexity is harder than making any single sentence sound good. Test on the hard cases first.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Baseline analysis | Pitfall 11: Not measuring what model already does | Quantify pause distribution, pitch range, breath gaps before ANY implementation |
| Pause/delay injection | Pitfall 4: Timing too uniform or wrong placement | Variable durations with jitter; semantic-aware placement; fill pauses with room tone |
| Pause/delay injection | Pitfall 8: Streaming double-pauses at chunk boundaries | Account for model-generated pauses; do not add on top |
| Prosody enhancement | Pitfall 2: Sing-song over-modulation | Do not manipulate pitch at waveform level; use reference audio or embedding-level adjustments |
| Prosody enhancement | Pitfall 11: Fighting model's learned prosody | Work with model capabilities, not against them |
| Breathing/filler eval | Pitfall 3: Overuse or uncanny synthetic breaths | Audit existing model behavior first; hard cap filler density; skip if quality is not exceptional |
| Breathing/filler eval | Pitfall 1: Pushing into uncanny valley | A/B test against unmodified baseline; err on side of fewer, not more |
| Post-processing | Pitfall 5: Compression pumping, EQ resonance, streaming artifacts | Correct signal chain order; carry filter state; subtract rather than add |
| Post-processing | Pitfall 10: Room tone mismatch | Match reference audio acoustics; continuous across chunks |
| All phases | Pitfall 6: Demo effect / cherry-picked test cases | Adversarial test corpus; measure worst case, not average; regression test |
| All phases | Pitfall 7: Consistency collapse across utterances | Lower temperature; fixed seed per request; per-sentence profiling |
| All phases | Pitfall 1: Uncanny valley amplification | Incremental feature addition; A/B test each feature independently |

---

## The Cardinal Rule

**Less is more.** The natural instinct is to add features until the voice sounds human. The correct approach is to add as few features as possible, each validated independently against the baseline. A voice with one well-tuned naturalness feature sounds better than a voice with five mediocre ones.

Every feature added is a feature that can go wrong. Every feature that goes wrong makes the entire output sound less natural than if no naturalness features were present at all. The threshold for "this feature improves things" must be: it improves quality on at least 95% of diverse test inputs AND does not degrade quality on any significant subset.

---

## Confidence Assessment

| Pitfall | Confidence | Basis |
|---------|-----------|-------|
| Uncanny valley amplification | HIGH | Confirmed by multiple academic studies and industry practitioners; non-monotonic uncanniness function experimentally verified |
| Over-engineered prosody | HIGH | Documented across TTS literature; confirmed by research showing separate prosody models degrade quality |
| Filler/breathing overuse | HIGH | Quantified threshold (1.3% filler rate) from telemarketing study; XTTS v2 hallucination reports confirm existing artifact risk |
| Pause timing failures | MEDIUM | Consensus across practitioner sources; specific duration thresholds are approximations needing project-specific tuning |
| Post-processing artifacts | MEDIUM | Signal chain principles from audio engineering well-established; streaming-specific filter state issue confirmed in codebase |
| Demo effect | HIGH | Extensively documented across voice AI industry; multiple 2025-2026 practitioner reports confirm demo-to-production gap |
| Consistency collapse | MEDIUM | Confirmed by TTS evaluation studies; specific phoneme interactions need project-specific testing |
| Streaming naturalness breakage | MEDIUM | Confirmed by SpeakStream, Marvis TTS research; specific interactions with Fish Speech's pipeline need testing |
| Vocal fry implementation | MEDIUM | Academic literature confirms vocoder difficulties; skip recommendation based on scope analysis |
| Room tone mismatch | LOW | General audio engineering principle; Fish Speech-specific impact needs testing |
| Features fighting the model | MEDIUM | Architectural principle confirmed by research on separate vs. joint prosody models; Fish Speech-specific model behavior not tested |

---

## Sources

- [Sesame: Crossing the Uncanny Valley of Conversational Voice](https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice) -- Contextual awareness for naturalness; CSM architecture
- [Springer: Speech Synthesis and Uncanny Valley](https://link.springer.com/chapter/10.1007/978-3-319-10816-2_72) -- Experimental confirmation of vocal uncanny valley
- [ScienceDirect: Deviation from Typical Organic Voices](https://www.sciencedirect.com/science/article/pii/S2451958824000630) -- Non-monotonic uncanniness function in voice perception
- [Talkdesk: Voice AI - The Case for Artificial Imperfection](https://www.talkdesk.com/blog/voice-ai-case-artificial-imperfection/) -- Production vs. demo quality gap
- [Medium: Why Most AI Voice Deployments Fail After the Demo](https://medium.com/@marketing_34023/why-most-ai-voice-deployments-fail-after-the-demo-a2341a93b44e) -- Demo effect analysis
- [Chanl: The Voice AI Quality Crisis](https://www.channel.tel/blog/voice-ai-quality-crisis) -- Production deployment failure patterns
- [Rime AI: Filler Words - A Secret Facet of Conversational Realism](https://www.rime.ai/blog/filler-words-a-secret-facet-of-conversational-realism/) -- Role and dangers of filler words in TTS
- [Picovoice: Complete Guide to TTS Technology (2025)](https://picovoice.ai/blog/complete-guide-to-text-to-speech/) -- Prosody modeling challenges
- [Medium: The Persistent Challenge of Prosody Modeling](https://medium.com/@shukla.vjs/the-persistent-challenge-of-prosody-modeling-in-advanced-natural-language-processing-systems-44e8edbeb6d9) -- Text-speech modality gap in prosody
- [APXML: TTS Prosody Modeling and Control Techniques](https://apxml.com/courses/speech-recognition-synthesis-asr-tts/chapter-4-advanced-text-to-speech-synthesis/prosody-modeling-control-tts) -- Implicit vs. explicit prosody modeling tradeoffs
- [Milvus: How Does Pitch Control Affect TTS Output Quality](https://milvus.io/ai-quick-reference/how-does-pitch-control-affect-tts-output-quality) -- Pitch control quality impact
- [ElevenLabs: Troubleshooting](https://elevenlabs.io/docs/resources/troubleshooting) -- Stability/similarity slider artifact management
- [ElevenLabs: Voice Settings](https://elevenlabs-sdk.mintlify.app/speech-synthesis/voice-settings) -- Parameter interaction effects
- [Deepgram: Handling Audio Issues in TTS](https://developers.deepgram.com/docs/handling-audio-issues-in-text-to-speech) -- Streaming audio artifact handling
- [Deepgram: Text Chunking for TTS Optimization](https://developers.deepgram.com/docs/text-chunking-for-tts-optimization) -- Boundary detection best practices
- [SpeakStream: Streaming TTS with Interleaved Data](https://arxiv.org/html/2505.19206v1) -- Streaming quality degradation vs. batch
- [OpenReview: CLaM-TTS](https://openreview.net/pdf?id=ofzeypWosV) -- Codec language model artifact patterns
- [EmergentTTS-Eval](https://arxiv.org/html/2505.23009v1) -- TTS model failure patterns on complex inputs
- [GitHub: coqui-ai/TTS Discussion #4146](https://github.com/coqui-ai/TTS/discussions/4146) -- XTTS v2 hallucination artifacts and workarounds
- [GitHub: coqui-ai/TTS Discussion #2742](https://github.com/coqui-ai/TTS/discussions/2742) -- Transformer-based TTS hallucination patterns
- [ResearchGate: HMM-based Synthesis of Creaky Voice](https://www.researchgate.net/publication/258327995_HMM-based_synthesis_of_creaky_voice) -- Vocal fry synthesis challenges
- [Respeecher: Four Common Synthetic Speech Problems](https://www.respeecher.com/blog/four-common-synthetic-speech-problems-solve-them) -- Prosody and emphasis failures
- [FutureBeeAI: Evaluating TTS Voice Consistency](https://www.futurebeeai.com/knowledge-hub/evaluate-tts-voice-consistency) -- Multi-layered consistency evaluation
- [WellSaid Labs: Naturalness as Primary Driver](https://www.wellsaid.io/resources/blog/naturalness-primary-driver-synthetic-voice-quality) -- MOS evaluation limitations
