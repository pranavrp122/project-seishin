# Emotion-Aware TTS Prompt Formatting Guide

> **Purpose**: This guide defines every formatting rule used to generate tagged TTS training
> sentences for Fish Audio S2 Pro LoRA fine-tuning. The text formatting (punctuation, sentence
> length, structure, word choice) must reinforce the emotion tag — the text IS the prosody
> instruction. Mismatched cues (calm tag + exclamation-heavy text) create conflicting signals
> that degrade synthesis quality.
>
> **Usage**: Feed this guide as a system prompt to an LLM (Claude, etc.) when generating new
> training sentences. Every rule here was empirically validated against a 7,625-sample dataset.

---

## Table of Contents
1. [Core Principle: Punctuation = Prosody](#core-principle-punctuation--prosody)
2. [Tag System Rules](#tag-system-rules)
3. [High Energy Emotions](#high-energy-emotions)
4. [Low Energy Emotions](#low-energy-emotions)
5. [Physical / Vocal Expressions](#physical--vocal-expressions)
6. [Controlled Emotions](#controlled-emotions)
7. [Mid-Sentence Tag Placement](#mid-sentence-tag-placement)
8. [Emphasis Word Placement](#emphasis-word-placement)
9. [Sentence Length & Duration Variation](#sentence-length--duration-variation)
10. [Tag Distribution Targets](#tag-distribution-targets)
11. [Category Definitions](#category-definitions)
12. [Tag Translation Matrix](#tag-translation-matrix)
13. [Quality Checklist](#quality-checklist)

---

## Core Principle: Punctuation = Prosody

The TTS model reads punctuation as prosodic instruction. Every punctuation mark produces a
distinct acoustic effect. Matching punctuation to emotion is non-negotiable.

| Punctuation | Prosodic Effect | Best For | Avoid With |
|---|---|---|---|
| `.` | Full stop, downward intonation, deliberate pause | Confidence, anger (staccato), calm, sadness (soft landing), sarcasm (deadpan) | — |
| `!` | Energy spike, upward attack, emphasis | Happy, excited, surprised, angry (peaks), shouting, cheerful | Sad, exhausted, whisper, calm, sarcastic, warm |
| `...` | Hesitation, trailing off, lingering pause (upbeat/neutral energy) | Sarcasm (timing), playful trailing, mild surprise | Excited, confident, calm, professional, angry |
| `.....` | Deep hesitation, drawn-out silence, emotional weight | Nervous, sad, tired, whisper, sigh, exhausted, calm, analytical, professional, thoughtful, concerned | Excited, happy, cheerful, angry, shouting |
| `-` | Pause, breath break, self-interruption, thought redirect | Angry, nervous, surprised, exhausted, laughing/chuckle, self-correction | Calm, professional (unless structured aside) |
| `,` | Brief breath pause, clause linking | Warm (soft flow), calm, nervous (piling up), sad (meandering) | Angry (too flowing), excited (too slow) |
| `?` | Rising intonation, uncertainty or engagement | Surprised, nervous, playful (teasing), rhetorical | — |
| `?!` | Shocked disbelief — simultaneous question + exclamation | Surprised (disbelief/shock subtype ~20-25% of surprised lines) | Calm, sad, analytical, professional, whisper |

### Punctuation Allocation by Emotion

These are target rates validated against the dataset. The percentages indicate what share of
lines with that emotion tag should contain the punctuation mark.

| Emotion | `!` Rate | `...` Rate | `.....` Rate | `-` Rate | `?` Rate |
|---|---|---|---|---|---|
| [excited] | 80-90% | <5% | 0% | 10-15% | 15-25% |
| [happy] | 70-80% | <10% | 0% | 5-10% | 15-20% |
| [cheerful] | 60-70% | <10% | 0% | 5-10% | 15-25% |
| [surprised] | 50-60% | 10-15% | 0% | 20-30% | 20-30% (some `?` → `?!`, ~20-25% of lines) |
| [angry] | 55-65% | <5% | 0% | 25-35% | 15-25% |
| [shouting] | 85-95% | <3% | 0% | 10-15% | 5-10% |
| [sad] | <5% | <5% | 35-45% | 10-15% | 10-15% |
| [exhausted] | <5% | <5% | 60-70% | 10-15% | 5-10% |
| [nervous] | <10% | <5% | 60-70% | 25-35% | 20-30% |
| [tired] | <5% | <5% | 50-60% | 10-15% | 5-10% |
| [sarcastic] | <10% | 15-25% | 0% | 5-10% | 15-25% |
| [whisper] | <5% | <5% | 15-25% | 5-10% | 10-15% |
| [sigh] | <5% | <5% | 30-45% | 10-15% | 5-10% |
| [confident] | 5-10% | <5% | 0% | <5% | 5-10% |
| [calm] | <5% | 0% | 15-25% | <5% | 5-15% |
| [analytical] | <5% | 0% | 20-30% | <5% | 5-10% |
| [professional] | <5% | 0% | 15-25% | <5% | 5-10% |
| [warm] | <10% | 10-20% | 0% | 5-10% | 10-15% |
| [playful] | 30-45% | 10-20% | 0% | 15-25% | 20-30% |

### Exclamation Mark (`!`) Placement Logic

Not every sentence "deserves" a `!`. The decision is emotion-specific and follows these rules:

#### Angry Sentences Ending with `.`

1. **Check for forceful language** → change `.` to `!`
   - Forceful words: *dare, how dare, stop, enough, never, don't, get out, shut, leave, warning, swear, sick of, had it, fed up, disgusting, unacceptable, unbelievable, ridiculous, last straw, crossed a line, ruined, destroyed, broke, betrayed, lied, disrespectful, right now, this instant, I mean it, do not, how many times, I told you, every single, can't believe, went behind, lost it, own up, walk out, gave you every, tested me, pushing me, what were you, the nerve, the audacity, excuse, one job, promised, confidential, blabbed, threw away, threw out, wasted, one more time*
   - Accusatory questions phrased as statements: "are you serious", "are you kidding", "what is wrong"

2. **Check for cold/staccato anger** → keep `.` (overrides forceful check)
   - Cold words: *fine, done, over, leave, goodbye, that's it, we're done, I'm done, forget it, whatever, noted, understood, interesting*
   - Cold anger is quiet and controlled — the period IS the weapon

3. **Neither forceful nor cold** → 30% random chance of `!`
   - Prevents monotony while keeping most neutral-angry lines with `.`

4. **Angry rant sentences** — Some angry lines use "and" chains for building rage energy. These always end with `!`. Structure: accusation + "and" + escalation + "and" + final blow. Target: ~6-8 rant-style lines in the dataset.

#### Shouting Sentences Ending with `.`
- 85% of shouting lines get `.` → `!` (shouting almost always = exclamation)
- The remaining 15% keep `.` for variety — forceful declarative shouts that land harder with a period

#### Chuckle Sentences Ending with `.`
- **Energy-paired** (chuckle + happy/excited/playful/cheerful/amused): 45% get `!`
  - These are big laughs, delighted reactions, can't-contain-it energy
- **Soft-paired** (chuckle + gentle/tender/sad/whisper): never get `!`
  - These are quiet chuckles, fond smiles, soft humor
- **Unpaired or warm-paired**: 15% get `!`
  - Light amusement occasionally bubbles up

#### Playful Sentences Ending with `.`
- **Teasing/daring language** → always `!`
  - Teasing words: *bet you, dare, watch me, try me, can't handle, you think, good luck, game on, bring it, I swear, mine now, no take backs, not even sorry, fight me, come at me, catch me*
- **Other playful lines**: 20% random chance of `!`

#### Emotions That Should NEVER Get `!`
- `[sad]`, `[exhausted]`, `[whisper]`, `[calm]`, `[professional]`, `[analytical]`
- `[sarcastic]` — the deadpan `.` is funnier than `!`

#### Multiple Exclamation Marks (`!!` or `!!!`)

Double and triple exclamation marks indicate **extreme emphasis** and heightened energy. Use with high-energy emotions:

- **`!!`** (double): Used for [excited], [happy], [cheerful], [playful], [laughing], [chuckle] when already ending with `!`
  - Adds emphasis without being over-the-top
  - Applied to ~50% of high-energy sentences
  - Example: `[excited][happy] Oh my gosh, you actually remembered!!`

- **`!!!`** (triple): Reserved for [shouting] and extreme rage peaks only
  - Rare — only ~5-10% of shouting lines
  - Example: `[shouting] Get your hands off that right now!!!`

- **Never use multiple marks with**: [sad], [exhausted], [whisper], [calm], [sarcastic]

#### Current `!` Rates (Post-Pass)
| Emotion | `!` Rate | `!!` Rate | Notes |
|---|---|---|---|
| [excited] | ~85% | ~60% of `!` become `!!` | Excitement is peak energy |
| [happy] | ~78% | ~45% of `!` become `!!` | High energy reinforcement |
| [cheerful] | ~80% | ~50% of `!` become `!!` | Consistent with happy |
| [shouting] | ~95% | ~8% become `!!!` | Almost always, highest emphasis rare |
| [surprised] | ~69% | ~20% of `!` become `!!` | Selective emphasis for shock |
| [angry] | ~62% | <5% become `!!` | Cold anger stays single, rants peak at `!` |
| [playful] | ~47% | ~40% of `!` become `!!` | Playful energy amplified |
| [laughing] | ~70% | ~55% of `!` become `!!` | Laughter intensity emphasis |
| [chuckle] | ~44% | ~50% of `!` become `!!` | Energy-paired chuckles amplified |

---

## Tag System Rules

### Format
- Each tag gets its own brackets: `[happy][excited]` — never `[happy, excited]`
- Tags are case-sensitive and always lowercase: `[sigh]` not `[Sigh]`
- Maximum 2 tags at sentence start, maximum 1 mid-sentence tag
- Total tags per line: 1-3 (never more than 3)

### Tag Field
Every JSONL line has a `tag` field that concatenates ALL tags from the `text` field:
```json
{"id": 1, "tag": "[warm]", "text": "[warm] Hey, how are you?"}
{"id": 2, "tag": "[calm][surprised]", "text": "[calm] The data looks normal... [surprised] wait, what is that spike?"}
```
The `tag` field must match exactly what appears in `text` — no extras, no missing tags.

### Physical vs. Emotion Tags
- **Emotion tags** set the overall feeling: `[happy]`, `[sad]`, `[angry]`, `[warm]`, etc.
- **Physical tags** describe a vocal action: `[sigh]`, `[chuckle]`, `[laughing]`, `[gasp]`, `[inhale]`, `[whisper]`
- Physical tags should almost always be paired with an emotion tag
- The emotion sets WHY, the physical tag sets HOW
- Unpaired physical tags (physical tag without any emotion) are allowed but should be rare (<2% of lines)

### Tag Pairing Rules
Physical tags pair naturally with specific emotions:

| Physical Tag | Natural Emotion Pairs | Why |
|---|---|---|
| `[sigh]` | [tired], [exhausted], [sad], [frustrated], [angry] | Sighing = resignation, fatigue, burned-out anger |
| `[chuckle]` | [happy], [playful], [warm], [sarcastic] | Chuckling = amusement, affection, dry humor |
| `[laughing]` | [happy], [excited], [nervous] | Laughing = joy, can't-contain-it energy, nervous release |
| `[gasp]` | [surprised], [nervous], [excited] | Gasping = sudden shock, panic, overwhelmed excitement |
| `[inhale]` | [nervous], [confident], [calm] | Inhaling = steadying breath, bracing, gathering courage |
| `[whisper]` | [gentle], [tender], [sad], [nervous], [warm] | Whispering = intimacy, vulnerability, fear of being heard |

---

## High Energy Emotions

### [excited]
- **Sentence length**: Short (5-12 words). Rapid-fire succession of thoughts.
- **Punctuation**: `!` on 80-90% of sentences. Rhetorical `?` for engagement. Minimal `,` — excitement doesn't pause.
- **Structure**: Declarative bursts. Fragments ("So good!"). Rhetorical questions ("Isn't that amazing?").
- **Word patterns**: Intensifiers (so, really, absolutely, literally). Repetition ("This is great, just great!"). Heavy contractions. Emphasis words ("even", "actually").
- **DO NOT**: Use `...` (excited people don't trail off). Use long meandering sentences. Use hedging.
- **Mid-sentence shift**: Place [chuckle] or [gasp] at moments of peak excitement.
- **Terminal punctuation**: Always `!` or `?` — never `.` or `...`
- **Example**: `Oh! This is wonderful! I can't believe it actually worked! You're going to love this!`

### [happy]
- **Sentence length**: Short to medium (8-15 words). Bouncy rhythm with varied lengths.
- **Punctuation**: `!` on 70-80% of sentences (not every sentence). `,` to chain enthusiastic clauses. Some `?` for engagement.
- **Structure**: Complete but energetic sentences. Mix declarations with questions. Sharing good things.
- **Word patterns**: Contractions throughout. Positive vocabulary. Light intensifiers. "Even" for emphasis ("that made it even better!").
- **Mid-sentence shift**: [warm] or [chuckle] for moments where happiness softens into tenderness or laughter.
- **Terminal punctuation**: Mostly `!`, some `.` for grounded happy moments.
- **Example**: `I made pancakes shaped like little stars! It's Saturday and we deserve something wonderful for breakfast.`

### [cheerful]
- **Sentence length**: Short to medium. Inviting and warm with energy.
- **Punctuation**: Light `!` (60-70%, less aggressive than excited). Friendly `?`. Standard `,`.
- **Structure**: Invitations, suggestions, sharing good news. Warmth + energy combined.
- **Mid-sentence shift**: [happy] or [excited] when cheerful energy builds.
- **Example**: `Morning sunshine! I already made your coffee the way you like it. How'd you sleep?`

### [angry]
- **Sentence length**: Very short (3-8 words, target average ≤15 words). Staccato rhythm. Hard stops.
- **Punctuation**: Hard `.` periods (declarative force, cold anger). `!` at forceful peaks (55-65%) — any sentence with accusatory/command language gets `!`, cold staccato anger keeps `.`. `-` for self-interruption ("I told you to - forget it."). Minimal `,` — anger doesn't pause to breathe. NO `...` — anger doesn't trail off, it cuts.
- **Structure**: Imperatives ("Stop. Now."). Accusatory questions ("What were you thinking?"). Fragments and incomplete threats. Short declaratives stacked.
- **Word patterns**: Repetition for hammering ("No. No, I said no."). No filler words — anger is direct. Monosyllabic preference. No hedging whatsoever.
- **DO NOT**: Use `...` (anger cuts, doesn't trail). Use long flowing sentences (>15 words). Use hedging words. Use polite qualifiers.
- **Shortening rule**: If an angry sentence exceeds 15 words, find the first natural sentence break (`.`, `!`, `?`, ` - `) after word 5 and truncate there. Angry speech is clipped.
- **Rant variation**: A small number (~6-8) of angry lines use "and" chain structure for escalating rage. These are longer exceptions to the short-sentence rule: accusation + "and" + escalation + "and" + final blow. Always end with `!`. Example: `You went behind my back on this and lied about it and then had the nerve to act surprised when I found out!`
- **Mid-sentence shift**: [sigh] for anger burning into exhaustion. [shouting] for escalation.
- **Example (staccato)**: `That's enough. I told you three times. Three. And you still didn't listen.`
- **Example (rant)**: `I trusted you with every single thing I had and you threw it all away and you didn't even have the decency to tell me!`

### [shouting]
- **Sentence length**: Short (3-10 words). Commands and accusations.
- **Punctuation**: Heavy `!` (85-95%). Hard `.` between bursts. `-` for interrupted shouts.
- **Structure**: Imperatives, demands, warnings. Raw and unfiltered.
- **Mid-sentence shift**: [angry] preceding the shout, or [inhale] before the burst.
- **Contradictions**: NEVER pair with [calm], [whisper], [gentle], [tender], or [warm]. These are mutually exclusive.
- **Example**: `Get out! I don't want to hear it! Not one more word!`

### [surprised]
- **Sentence length**: Very short initial reaction (1-5 words), then medium follow-up as brain catches up.
- **Punctuation**: `!` on the first beat (70-80%). `?` for disbelief (30-40%). `-` for incomplete thoughts as brain processes (20-30%).
- **Structure**: Fragment first ("Wait, what!"), then full question ("How did that happen?"). Two-phase: reaction then processing.
- **Word patterns**: Interjections (oh, wait, no way, what). Repetition of the surprising element.
- **Mid-sentence shift**: [gasp] before the reaction word. [excited] or [happy] if positive surprise.
- **Example**: `Wait - are you serious? That's... I didn't expect that at all! How long have you known?`

---

## Low Energy Emotions

### [sad]
- **Sentence length**: Medium to long. Thoughts drift and wander. Occasional very short defeated fragments ("I know.").
- **Punctuation**: `...` heavily (35-45% of sad lines) — trailing off is the signature. Soft `.` (not forceful). NO `!`. Many `,` for slow meandering clauses.
- **Structure**: Incomplete thoughts that trail into nothing. Past-tense reflection. Rhetorical self-questioning ("What was the point...").
- **Word patterns**: Hedging (I guess, I suppose, maybe). Understated language. Self-correction ("It was fine... I mean, not really.").
- **DO NOT**: Use `!`. Use short punchy sentences (unless defeated fragments). Use confident declaratives.
- **Terminal punctuation**: `...` or soft `.` — never `!`
- **Mid-sentence shift**: [whisper] for trailing into quiet. [sigh] for resigned exhale mid-thought.
- **Example**: `I don't know... I thought things would be different by now. I guess I just... hoped for too much.`

### [exhausted]
- **Sentence length**: Very short. Fragments dominate. Minimal effort to form complex thoughts.
- **Punctuation**: `...` between phrases (60-70% — not hesitation, running out of energy). `.` that feels like collapse. No `!`. Minimal `,` because sentences are too short to need them.
- **Structure**: Fragments ("So tired."). Subject-dropping ("Can't do this anymore." not "I can't do this anymore."). Minimal complete sentences.
- **Word patterns**: Monosyllabic preference. Contractions. Repetition from cognitive fatigue ("I just... I just need to rest.").
- **DO NOT**: Use `!`. Use long well-formed sentences. Use energetic vocabulary.
- **Mid-sentence shift**: [sigh] for exhale moments. [whisper] as energy fades completely.
- **Example**: `I'm done... can't keep going. Just... give me a minute. Please.`

### [nervous]
- **Sentence length**: Variable — starts medium, then fragments as anxiety spikes. Run-on sentences when spiraling.
- **Punctuation**: `...` for hesitation (60-70%: "Well... the thing is..."). `-` for self-correction (25-35%: "I was going to - I mean, I thought about -"). `,` piling up in anxious run-ons. `?` seeking reassurance (20-30%).
- **Structure**: False starts. Self-interruptions. Backtracking ("No wait, that's not what I meant."). Over-qualifying.
- **Word patterns**: Filler words (well, um, I mean, you know). Hedging (sort of, kind of, maybe, I think). Apologetic openings ("Sorry, I just...").
- **Dash insertion rule**: ~30% of nervous lines should have a `-` replacing a comma at a natural self-correction point. The text after the dash should feel like a course-correction or second thought.
- **Mid-sentence shift**: [gasp] for sudden panic. [inhale] for trying to steady breathing. [whisper] for shrinking.
- **Example**: `Um, so... the thing is, I wasn't sure if - I mean, I thought maybe we could, you know... try a different approach? If that's okay.`

---

## Physical / Vocal Expressions

> Physical tags describe a vocal action, not a feeling. They should almost always be paired
> with an emotion tag. The emotion tag sets the WHY, the physical tag sets the HOW.

### [sigh]
- **Sentence length**: Short to medium post-sigh. The sigh itself is a pause-beat.
- **Punctuation**: `...` immediately after sigh placement to create exhale pause. `.` heavy afterward (resigned). Low-energy punctuation.
- **Structure**: Concessive statement ("Fine, I'll do it.") or resigned observation. Short responses — the sigh carries emotional weight.
- **Word patterns**: "Fine," "alright," "okay" as openers post-sigh.
- **Pair with**: [tired], [sad], [exhausted], [angry] (burned out anger), [frustrated]
- **Placement logic**: Place at start for whole-sentence resignation. Place mid-sentence at the pivot where a character gives up fighting: after "but", after an objection, at a realization of futility.
- **Cross-category**: Must appear in ALL three categories (A, B, C). Sighs happen in personal, professional, and dramatic contexts.
- **Example start**: `[tired][sigh] ... Alright. Fine. I'll take care of it. Again.`
- **Example mid**: `[angry] I spent three hours debugging that and - [sigh] you know what, never mind.`

### [whisper]
- **Sentence length**: Short. Whispers are effortful and intimate.
- **Punctuation**: `...` sparingly for trailing. No `!` (contradicts register). `,` for breath-pacing (whispering needs more breaths).
- **Structure**: Imperative or confiding ("Don't move." / "I need to tell you something."). Brief questions.
- **Word patterns**: Simple vocabulary. Direct. No filler words (too much effort to whisper them).
- **DO NOT**: Use `!`. Use long complex sentences. Use loud/energetic vocabulary.
- **Pair with**: [gentle], [tender], [sad], [nervous], [warm]
- **Contradictions**: NEVER pair with [shouting], [angry], [excited]. These are mutually exclusive.
- **Placement logic**: Place at start for entire whispered line. Place mid-sentence where the speaker's voice drops — at a confession, a secret, an intimate aside. Often after `...` as voice trails down.
- **Example start**: `[gentle][whisper] Hey... come here. I need to tell you something.`
- **Example mid**: `[warm] I know you're scared but... [whisper] I'm right here, okay?`

### [chuckle]
- **Sentence length**: Short. Laughter breaks up speech into fragments.
- **Punctuation**: `-` mid-sentence where laugh interrupts ("I can't - okay, that was funny."). Light punctuation overall.
- **Structure**: Incomplete sentences. Restarts. Punchline then reaction.
- **Word patterns**: Interjections ("oh man", "okay okay"). Self-referential ("I'm sorry, I just can't stop.").
- **Pair with**: [happy], [warm], [playful], [sarcastic] (dry laugh)
- **Placement logic**: At the exact moment something funny is referenced or realized. Before the reaction, not after. Mid-sentence chuckles break the rhythm — they should interrupt a thought, not end it. Place at the funniest or most absurd part of the sentence.
- **Cross-category**: Must appear in ALL three categories. People chuckle during casual chat (A), dry professional observations (B), and dramatic irony (C).
- **Example start**: `[playful][chuckle] Oh come on, you cannot be serious right now.`
- **Example mid**: `[warm] You absolutely cannot wear that shirt with those pants - [chuckle] I say this with love.`

### [laughing]
- **Sentence length**: Very short. Speech barely survives through laughter.
- **Punctuation**: `-` interruptions everywhere. Sentence fragments. Restarts with "okay" or "I'm sorry."
- **Structure**: Almost incoherent at peak. Trying to speak but failing. Multiple attempts.
- **Pair with**: [happy], [excited], [nervous] (nervous laughter)
- **Placement logic**: Start for lines that are entirely laughter-soaked. Mid-sentence where the speaker loses composure — after the funniest word/phrase, causing the rest to dissolve into fragments.
- **Example**: `[happy][laughing] I can't - okay - I'm sorry, the look on your face - I just can't!`

### [gasp]
- **Sentence length**: 1-3 word reaction, then medium follow-up.
- **Punctuation**: `!` on reaction word. `-` if gasp cuts off previous thought. No `...` (gasps are sudden, not trailing).
- **Structure**: Pure exclamatory fragment first, then question or declaration.
- **Word patterns**: "Oh!" / "No!" / "Wait!" as the gasp-word.
- **Pair with**: [surprised], [nervous], [excited]
- **Placement logic**: Right before the shocking realization word. Mid-sentence gasps work at the exact pivot where new information hits — the text should change direction after the gasp.
- **Example**: `[surprised] The test results came back and - [gasp] oh! That can't be right.`

### [inhale]
- **Sentence length**: The inhale is a pre-speech beat. Following speech is medium, deliberate.
- **Punctuation**: `...` before the first word (breath-gathering). `,` heavy as speaker measures words.
- **Structure**: Complete, considered statement follows. The breath signals importance.
- **Word patterns**: "Okay..." or "Right..." as bridge. Often precedes difficult news or decisions.
- **Pair with**: [nervous], [confident] (steadying breath), [calm]
- **Placement logic**: At start = bracing before difficult speech. Mid-sentence = gathering courage at a pivot point. The inhale creates a beat of silence that makes the following words land harder.
- **Example**: `[nervous][inhale] ... Okay. Here's the thing. I need to tell you something important.`

---

## Controlled Emotions

### [warm] / [gentle] / [tender]
- **Sentence length**: Medium. Not rushed, not dragging. Flowing and complete.
- **Punctuation**: `,` for soft pauses. `...` sparingly for tender trailing (10-20%). No `!`. Gentle `.` closings.
- **Structure**: Complete sentences. Endearments and reassurances. Questions as invitations ("How are you feeling?"). Second-person ("You did so well.").
- **Word patterns**: Soft vocabulary (gentle, easy, okay, here). Reassuring phrases. No jargon. Emphasis words: "even" ("love you even more"), "just" ("I just want you to know"), "truly" ("truly special").
- **DO NOT**: Use `!`. Use staccato short sentences. Use sharp or technical language.
- **Mid-sentence shift**: [whisper] for intimate moments. [chuckle] for affectionate humor.
- **Example**: `Hey, it's okay. You don't have to worry about that right now. Just take your time, alright?`

### [calm] / [professional]
- **Sentence length**: Medium to long. Well-formed, grammatically correct.
- **Punctuation**: Standard `.` and `,`. No `!`. No `...` (<8% tolerance for natural pauses). Dashes only for structured asides.
- **Structure**: Declarative statements. Logical progression. Structured questions.
- **Word patterns**: No filler words. Minimal contractions. Precise vocabulary. No repetition. No hedging.
- **DO NOT**: Use `...`. Use `!`. Use fragments. Use filler words. Use emotional vocabulary.
- **Contradictions**: NEVER pair with [shouting], [angry], [excited].
- **Ellipsis removal rule**: If a calm/professional line contains `...`, replace with `,` (if mid-sentence) or `.` (if at end). Exception: keep `...` only if it genuinely represents a measured pause in an otherwise calm sentence.
- **Example**: `The results are consistent with our initial projections. I recommend proceeding with the second phase as planned.`

### [confident]
- **Sentence length**: Medium. Declarative. Neither curt nor rambling.
- **Punctuation**: Strong `.`. Minimal `?`. No `...` (<5%). `!` only for genuine emphasis (5-10%).
- **Structure**: Subject-verb-object. Active voice exclusively. Assertions, not qualifications.
- **Word patterns**: No hedging (remove "I think," "maybe," "sort of"). Strong verbs. First-person ownership. "This will work." not "I think this might work."
- **DO NOT**: Use `...`. Use hedging. Use passive voice. Use filler words.
- **Ellipsis removal rule**: Same as calm — replace `...` with `,` or `.`
- **Example**: `I've reviewed the data. The approach is sound, and I stand behind the recommendation. Let's move forward.`

### [sarcastic]
- **Sentence length**: Medium setup + short punchline.
- **Punctuation**: Deadpan `.` (more sarcastic than `!`). `...` before ironic payoff for timing (15-25%). `,` for drawn-out delivery. No `!` (<10% — kills the deadpan).
- **Structure**: Setup + subversion. Apparent agreement then contradiction. Rhetorical questions ("Oh, you don't say?"). Flat observations.
- **Word patterns**: Exaggerated positives used negatively ("Oh, wonderful."). "Really" and "sure" as irony markers. Understatement. "Truly" for mock sincerity.
- **DO NOT**: Use `!` (kills the deadpan). Use genuine positive language. Use filler/hedging (sarcasm is deliberate).
- **Mid-sentence shift**: [chuckle] for dry laugh. [sigh] for "I can't even be bothered" energy.
- **Example**: `Oh, that's just perfect. No really, I love when everything falls apart at the last minute... truly inspiring.`

### [playful]
- **Sentence length**: Short to medium. Bouncy rhythm. Varied lengths for dynamic energy.
- **Punctuation**: Light `!` (30-45%). Teasing `?` (20-30%). `-` for quick asides (15-25%). `...` for dramatic teasing ("Guess what...") (10-20%).
- **Structure**: Questions, dares, challenges ("Bet you can't."). Conspiratorial framing ("Okay, so here's the thing.").
- **Word patterns**: Informal. Contractions. Hyperbole ("That's literally the best thing ever."). Tag questions ("Right?").
- **Mid-sentence shift**: [chuckle] for breaking into laughter. [whisper] for conspiratorial asides.
- **Example**: `Okay wait - you're not going to believe this. Guess who just showed up? I'll give you a hint... it's not who you think.`

### [analytical]
- **Sentence length**: Medium to long. Methodical and structured.
- **Punctuation**: Standard `.` and `,`. Rare `?` for hypothesis framing. No `!`, no `...`.
- **Structure**: Logical flow — premise, evidence, conclusion. "Based on X, Y suggests Z."
- **Word patterns**: Technical but accessible. Data references. Conditional language ("if... then...").
- **Note**: Translated to `[articulate][slow]` for Fish S2 Pro synthesis (removed [clear] due to generation instability).
- **Example**: `Based on the data, we should prioritize the memory allocation issue first. The latency correlation is too strong to ignore.`

### [emphasis]
- **Usage**: Used as a mid-sentence modifier to mark a key word or phrase for stress.
- **Placement**: Before the word(s) that need vocal emphasis.
- **Example**: `[confident] The tests all passed. [emphasis] Every single one.`

### [pause] / [short pause]
- **Usage**: Insert deliberate silence for dramatic or structural effect.
- **Placement**: Between clauses where a beat of silence adds weight.
- **Example**: `[calm] The investigation concluded. [pause] No evidence of tampering was found.`

---

## Mid-Sentence Tag Placement

Mid-sentence tags create emotion shifts within a single line. They represent moments where
a speaker's emotional state genuinely changes mid-thought. Tags affect all audio AFTER them,
so placement determines where the shift happens.

### Target Rate
~25% of all tagged lines should have a mid-sentence tag. This teaches the model to handle
emotion transitions within a single utterance.

### Natural Shift Pairs (start tag → valid mid-sentence tags)

| Start Emotion | Valid Mid-Sentence Shifts | Natural Pivot Words |
|---|---|---|
| [calm] | [surprised], [emphasis], [gasp] | "wait", "but", "actually", "hold on" |
| [happy] | [chuckle], [warm], [tender] | "and", "because", sentence break |
| [excited] | [gasp], [chuckle], [happy] | "and", "wait", sentence break |
| [angry] | [sigh], [exhausted], [shouting] | "but", " - ", sentence break |
| [sad] | [whisper], [sigh], [warm] | "...", "but", "I guess" |
| [nervous] | [gasp], [inhale], [whisper] | " - ", "...", "wait" |
| [confident] | [emphasis], [surprised], [pause] | "but", "and", sentence break |
| [sarcastic] | [chuckle], [sigh], [laughing] | "...", "but", sentence break |
| [playful] | [chuckle], [whisper], [excited] | " - ", "...", "wait" |
| [warm] | [whisper], [chuckle], [tender] | "...", "and", sentence break |
| [exhausted] | [sigh], [whisper] | "...", sentence break |
| [gentle] | [whisper], [chuckle], [warm] | "...", "and", sentence break |
| [tender] | [whisper], [sigh], [warm] | "...", "and", "because" |
| [cheerful] | [chuckle], [excited], [happy] | "and", "wait", sentence break |
| [analytical] | [emphasis], [pause], [surprised] | "but", "however", sentence break |
| [professional] | [emphasis], [pause] | "however", "importantly", sentence break |
| [surprised] | [happy], [excited], [gasp] | "and", "wait", sentence break |

### Insertion Points (Where to Place Mid-Tags)
Mid-sentence tags go at natural emotional pivot points. The algorithm for finding them:

1. **After `...`** — Trailing off creates a natural emotion shift. Speaker collects themselves and continues with a different feeling.
   - `[sad] I thought we'd have more time... [whisper] I guess not.`

2. **After ` - `** — Self-interruption = thought redirect. The dash is already a break in flow.
   - `[nervous] I was going to tell you but - [inhale] okay, here's what happened.`

3. **At sentence breaks (`[.!?] [A-Z]`)** — Complete thought ends, new emotional beat begins.
   - `[calm] The results look normal. [surprised] Wait, what is that spike?`

4. **After conjunctions** — "but", "and", "because" at natural clause boundaries.
   - `[angry] I did everything right but - [sigh] it still wasn't enough.`

### Placement Rules
1. Place mid-tag AFTER the pivot word/punctuation, not before
2. The text after the mid-tag must follow that emotion's formatting rules
3. Emotion shifts should feel like genuine emotional progression, not random jumps
4. Physical tags ([sigh], [chuckle], [gasp]) work especially well as mid-sentence tags because they represent involuntary reactions
5. Maximum 1 mid-sentence tag per line (keep it clean for training)
6. The shift should be "narratively plausible" — a speaker wouldn't go from [sad] to [excited] in one breath without a trigger

### Examples by Pattern

**Trailing into vulnerability:**
```
[warm] I know you're trying your best... [whisper] and that's all I need.
```

**Realization mid-thought:**
```
[calm] Everything seems fine on the surface. [surprised] Wait — these numbers don't add up at all.
```

**Anger burning out:**
```
[angry] I can't keep doing this. Every single time - [sigh] forget it. I'm done arguing.
```

**Humor breaking through:**
```
[sarcastic] Oh sure, because nothing says professional like showing up in sweatpants. [chuckle] Actually, respect.
```

**Nervous confession:**
```
[nervous] I probably should have mentioned this earlier but - [inhale] okay, don't be mad.
```

---

## Emphasis Word Placement

Emphasis words intensify emotional impact without changing meaning. They make sentences
feel more natural and emotionally committed. Use sparingly — oversaturation dulls the effect.

### Word Categories

| Word | Effect | Best Emotions | Example |
|---|---|---|---|
| "even" | Intensifies comparisons and contrasts | warm, tender, happy, excited | "that makes me love you even more" |
| "just" | Adds intimacy, softness, simplicity | warm, gentle, whisper, tender | "I just want you to know" |
| "genuinely" | Signals deep sincerity | warm, tender, grateful, happy | "I genuinely appreciate that" |
| "truly" | Elevates importance | warm, tender, sarcastic (ironic) | "truly special" / "truly delightful" (sarcasm) |
| "absolutely" | Maximum commitment | excited, confident, happy | "absolutely incredible" |
| "honestly" | Vulnerable authenticity | warm, nervous, sad | "honestly, I didn't expect this" |
| "actually" | Mild surprise, correction | surprised, playful, happy | "you actually did it!" |
| "literally" | Hyperbolic emphasis | excited, playful, surprised | "literally the best thing ever" |

### Placement Rules

1. **"even" before "more"**: When a warm/tender/happy sentence has "more" in a comparison context, add "even" before it. "love you more" → "love you even more". Only in genuinely emotional contexts — not sarcastic or neutral comparisons.

2. **"just" before verbs of desire**: In warm/gentle contexts, "I want to" → "I just want to", "I need to" → "I just need to". Creates softer, more intimate phrasing. Apply to ~30% of opportunities to avoid saturation.

3. **"genuinely" replacing "really"**: In sincere emotional contexts, "I really appreciate" → "I genuinely appreciate". More specific and heartfelt. Apply sparingly (~15% of opportunities).

4. **"truly" before impactful adjectives**: Before words like "special", "wonderful", "beautiful", "grateful" in warm contexts. Apply to ~20% of opportunities.

5. **"truly" in sarcasm**: "truly delightful", "truly inspiring" — ironic usage that strengthens deadpan delivery.

### Saturation Limits
- Don't apply more than one emphasis insertion per sentence
- If a sentence already has an intensifier (really, so, very), don't add another
- Target: ~5% of total lines get an emphasis word insertion
- Existing natural emphasis words should not be modified

---

## Sentence Length & Duration Variation

### Length Distribution (Target)
| Length | Word Count | ~Audio Duration | Share | Purpose |
|---|---|---|---|---|
| Short | 5-15 words | 3-6 seconds | 40% | Quick replies, emotional bursts, fragments |
| Medium | 15-35 words | 6-12 seconds | 40% | Conversational exchanges, explanations |
| Long | 35-60 words | 12-15 seconds | 20% | Monologues, complex thoughts, storytelling |

### Length by Emotion
| Emotion | Target Length | Why |
|---|---|---|
| [angry] | Very short (avg ≤15w) | Staccato rhythm, clipped speech |
| [excited] | Short (5-12w) | Rapid-fire bursts |
| [exhausted] | Very short (fragments) | Too tired for long sentences |
| [shouting] | Short (3-10w) | Commands, demands |
| [surprised] | Short reaction + medium follow-up | Two-phase processing |
| [calm] | Medium to long | Well-formed, measured |
| [professional] | Medium to long | Structured, complete |
| [sad] | Medium to long (with trailing) | Wandering thoughts |
| [nervous] | Variable (run-ons then fragments) | Anxiety pattern |

### Maximum Length Rule
No sentence should exceed 50 words. If a generated sentence exceeds this:
1. Find a natural sentence break (`.`, `!`, `?`, ` - `) between words 35-50
2. Truncate there
3. Ensure the remaining text has proper terminal punctuation

### Very Long Line Prevention
Lines over 40 words are flagged. They're acceptable at 20% of the dataset but should be
checked for naturalness — very few people speak 50+ words without pausing.

---

## Tag Distribution Targets

| Tags per line | Target % | Purpose |
|---|---|---|
| 0 tags | ~1.3% (100 lines) | Voice identity baseline — pure neutral speech |
| 1 tag | 35-40% | Clean single-emotion samples for baseline learning |
| 2 tags (both at start) | 35-40% | Emotion + physical pairing (e.g., [happy][chuckle]) |
| 2 tags (one mid-sentence) | 15-20% | Emotion shift training |
| 3 tags | 5-15% | Complex emotional scenes |
| 4+ tags | <2% | Rare, only for very complex emotional journeys |

### Untagged Lines (0 tags)
100 lines with no emotion tags. These are neutral, everyday sentences that train the model's
baseline voice identity without emotional coloring. They should be:
- Conversational but neutral in tone
- Varied in topic (weather, daily activities, observations)
- Standard punctuation (`.`, `,`, `?`)
- No emotional vocabulary
- Example: `The weather's been nice lately, I think I'll go for a walk after lunch.`

---

## Category Definitions

### Category A: Casual & Core Affection (40% of dataset)
Personal, emotional, relational. Conversations between close people — friends, family, partners.

**Primary tags**: [happy], [excited], [chuckle], [whisper], [sad], [warm], [gentle], [playful], [tender], [cheerful]

**Characteristics**:
- First and second person ("I", "you", "we")
- Contractions throughout
- Informal vocabulary
- Emotional honesty
- References to shared experiences, daily life, relationships
- Pet names, inside jokes, casual observations

**Example topics**: Morning greetings, compliments, comfort during hard times, shared laughter, love confessions, playful teasing, nostalgic reminiscing

### Category B: Technical & Reporting (30% of dataset)
Professional, analytical, informational. Work contexts, reporting, technical communication.

**Primary tags**: [analytical], [confident], [pause], [short pause], [emphasis], [calm], [professional]

**Characteristics**:
- Third person or impersonal ("the data shows", "results indicate")
- Formal vocabulary
- Minimal contractions
- Structured arguments
- Data references, metrics, percentages
- No emotional outbursts

**Example topics**: Performance reports, data analysis, project updates, technical explanations, recommendations, meeting summaries

### Category C: Heavy Acting & Physical (30% of dataset)
Dramatic, physically expressive, high-contrast emotions. Theatrical and extreme emotional states.

**Primary tags**: [sarcastic], [sigh], [inhale], [surprised], [angry], [exhausted], [nervous], [shouting], [laughing], [gasp]

**Characteristics**:
- Extreme emotions (rage, terror, euphoria, exhaustion)
- Physical reactions (gasping, sighing, laughing uncontrollably)
- Dramatic situations
- High punctuation variety
- Sentence fragments from emotional overwhelm
- Character voices and dramatic monologues

**Example topics**: Arguments, panic situations, exhaustion after long days, sarcastic observations, nervous confessions, shocked reactions

### Cross-Category Physical Tags
Physical tags ([sigh], [whisper], [chuckle], [gasp], [inhale], [laughing]) MUST appear
in all three categories to prevent the model from associating them with only one context:

| Physical Tag | Category A Use | Category B Use | Category C Use |
|---|---|---|---|
| [sigh] | Resignation in relationships | Frustration with work | Dramatic exhaustion |
| [chuckle] | Affectionate humor | Dry professional wit | Sarcastic/ironic laugh |
| [whisper] | Intimate confessions | Confidential information | Fear, secrecy |
| [gasp] | Surprise gifts/news | Unexpected data results | Shock, horror |
| [inhale] | Bracing for emotional talk | Preparing for presentation | Panic, steadying |
| [laughing] | Shared joy | Absurd work situation | Nervous/uncontrollable |

---

## Tag Translation Matrix

Some tags in the training data need translation for Fish S2 Pro synthesis. The `.lab` files
store the ORIGINAL tag (for LoRA training), but the synthesizer receives the translated version.

| Training Tag | Fish S2 Pro Translation | Why |
|---|---|---|
| `[sarcastic]` | `[deadpan][sarcastic][low pitch]` | S2 Pro needs multiple descriptors for sarcasm |
| `[analytical]` | `[articulate][slow]` | S2 Pro renders analysis better with explicit pacing (removed [clear] due to instability) |
| All other tags | Pass through unchanged | S2 Pro supports them natively |

**Important**: The LoRA model will learn the ORIGINAL simple tags. The translation only
happens at synthesis time in `factory_loop.py`. This keeps the training vocabulary clean.

---

## Quality Checklist

Run this checklist against any generated dataset before synthesis:

### Structural Checks
- [ ] Every line has valid JSON: `{"id": N, "category": "A/B/C", "tag": "...", "text": "..."}`
- [ ] Field order: id, category, tag, text
- [ ] No duplicate text bodies (strip tags, lowercase, compare)
- [ ] No broken brackets (unbalanced `[` and `]`)
- [ ] No non-ASCII characters outside tags
- [ ] Tag field matches all tags in text field exactly

### Distribution Checks
- [ ] Category A: 39-41% of total
- [ ] Category B: 29-31% of total
- [ ] Category C: 29-31% of total
- [ ] ~100 untagged (0-tag) lines
- [ ] 1-tag lines: 35-40%
- [ ] 2-tag lines: 40-50%
- [ ] 3-tag lines: 10-15%
- [ ] Mid-sentence tags: 23-27% of tagged lines

### Emotion-Punctuation Alignment
- [ ] [excited] lines: ≥75% contain `!`
- [ ] [happy] lines: ≥65% contain `!`
- [ ] [sad] lines: ≥30% contain `...`
- [ ] [exhausted] lines: ≥55% contain `...`
- [ ] [nervous] lines: ≥55% contain `...`
- [ ] [angry] lines: average word count ≤15
- [ ] [confident] lines: <10% contain `...`
- [ ] [calm] lines: <10% contain `...`
- [ ] [sarcastic] lines: <15% contain `!`
- [ ] [whisper] lines: <10% contain `!`

### Content Quality
- [ ] No template/repetitive phrasing (check 6-word prefix groups; max 2 per group)
- [ ] No slang that breaks character (bruh, dude, yo — remove entirely)
- [ ] "Honestly" used sparingly (≤100 occurrences)
- [ ] Natural filler preserved ("but like..." OK, random "like" as filler removed)
- [ ] Physical tags appear in all 3 categories
- [ ] No contradictory tag combos (calm+shouting, whisper+shouting)
- [ ] All lines have terminal punctuation (`.`, `!`, `?`, `...`)
- [ ] No comma-terminated sentences
- [ ] Emphasis words ("even", "just", "truly") used naturally, not over-saturated

### Sentence Length
- [ ] Short (≤15w): ~40%
- [ ] Medium (16-35w): ~40%
- [ ] Long (36-50w): ~20%
- [ ] No lines exceed 50 words
- [ ] Average: 15-20 words
