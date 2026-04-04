# Emotion-Aware TTS Prompt Formatting Guide

> Use this guide when generating tagged TTS training sentences. The text formatting
> (punctuation, sentence length, structure) must reinforce the emotion tag — the text
> IS the prosody instruction. Mismatched cues (calm tag + exclamation-heavy text)
> create conflicting signals that degrade synthesis quality.

---

## Core Principle: Punctuation = Prosody

| Punctuation | Prosodic Effect | Best For |
|---|---|---|
| `.` | Full stop, downward intonation, deliberate pause | Confidence, anger (staccato), calm, sadness (soft landing) |
| `!` | Energy spike, upward attack, emphasis | Happy, excited, surprised, angry (peaks), shouting |
| `...` | Hesitation, trailing off, lingering pause | Nervous, sad, tired, whisper, sarcasm (timing), sigh |
| `-` | Pause, breath break, self-interruption, thought redirect | Angry, nervous, surprised, exhausted, laughing/chuckle |
| `,` | Brief breath pause, clause linking | Warm (soft flow), calm, nervous (piling up), sad (meandering) |
| `?` | Rising intonation, uncertainty or engagement | Surprised, nervous, playful (teasing), rhetorical |

---

## High Energy Emotions

### [excited]
- **Sentence length**: Short (5-12 words). Rapid-fire succession of thoughts.
- **Punctuation**: `!` on most sentences. Rhetorical `?` for engagement. Minimal `,` - excitement doesn't pause.
- **Structure**: Declarative bursts. Fragments ("So good!"). Rhetorical questions ("Isn't that amazing?").
- **Word patterns**: Intensifiers (so, really, absolutely, literally). Repetition ("This is great, just great!"). Heavy contractions.
- **DO NOT**: Use `...` (excited people don't trail off). Use long meandering sentences.
- **Mid-sentence shift**: Place [chuckle] or [gasp] at moments of peak excitement.
- **Example**: `Oh! This is wonderful! I can't believe it actually worked! You're going to love this!`

### [happy]
- **Sentence length**: Short to medium (8-15 words). Bouncy rhythm with varied lengths.
- **Punctuation**: Well-placed `!` (not every sentence - about 60%). `,` to chain enthusiastic clauses. Some `?` for engagement.
- **Structure**: Complete but energetic sentences. Mix declarations with questions.
- **Word patterns**: Contractions throughout. Positive vocabulary. Light intensifiers.
- **Mid-sentence shift**: [warm] or [chuckle] for moments where happiness softens into tenderness or laughter.
- **Example**: `I made pancakes shaped like little stars! It's Saturday and we deserve something wonderful for breakfast.`

### [cheerful]
- **Sentence length**: Short to medium. Inviting and warm with energy.
- **Punctuation**: Light `!` (less aggressive than excited). Friendly `?`. Standard `,`.
- **Structure**: Invitations, suggestions, sharing good news. Warmth + energy combined.
- **Mid-sentence shift**: [happy] or [excited] when cheerful energy builds.
- **Example**: `Morning sunshine! I already made your coffee the way you like it. How'd you sleep?`

### [angry]
- **Sentence length**: Very short (3-8 words). Staccato rhythm. Hard stops.
- **Punctuation**: Hard `.` periods (declarative force). `!` only at rage peaks. `-` for self-interruption ("I told you to - forget it."). Minimal `,` - anger doesn't pause to breathe.
- **Structure**: Imperatives ("Stop. Now."). Accusatory questions ("What were you thinking?"). Fragments and incomplete threats.
- **Word patterns**: Repetition for hammering ("No. No, I said no."). No filler words - anger is direct. Short declaratives.
- **DO NOT**: Use `...` (anger doesn't trail off - it cuts). Use long flowing sentences. Use hedging words.
- **Mid-sentence shift**: [sigh] for anger burning into exhaustion. [shouting] for escalation.
- **Example**: `That's enough. I told you three times. Three. And you still didn't listen.`

### [shouting]
- **Sentence length**: Short (3-10 words). Commands and accusations.
- **Punctuation**: Heavy `!`. Hard `.` between bursts. `-` for interrupted shouts.
- **Structure**: Imperatives, demands, warnings. Raw and unfiltered.
- **Mid-sentence shift**: [angry] preceding the shout, or [inhale] before the burst.
- **Example**: `Get out! I don't want to hear it! Not one more word!`

### [surprised]
- **Sentence length**: Very short initial reaction (1-5 words), then medium follow-up as brain catches up.
- **Punctuation**: `!` on the first beat. `?` for disbelief. `-` for incomplete thoughts as brain processes.
- **Structure**: Fragment first ("Wait, what!"), then full question ("How did that happen?"). Two-phase: reaction then processing.
- **Word patterns**: Interjections (oh, wait, no way, what). Repetition of the surprising element.
- **Mid-sentence shift**: [gasp] before the reaction word. [excited] or [happy] if it's positive surprise.
- **Example**: `Wait - are you serious? That's... I didn't expect that at all! How long have you known?`

---

## Low Energy Emotions

### [sad]
- **Sentence length**: Medium to long. Thoughts drift and wander. Occasional very short defeated fragments ("I know.").
- **Punctuation**: `...` heavily - trailing off is the signature. Soft `.` (not forceful). Minimal `!`. Many `,` for slow meandering clauses.
- **Structure**: Incomplete thoughts that trail into nothing. Past-tense reflection. Rhetorical self-questioning ("What was the point...").
- **Word patterns**: Hedging (I guess, I suppose, maybe). Understated language. Self-correction ("It was fine... I mean, not really.").
- **DO NOT**: Use `!`. Use short punchy sentences (unless defeated fragments). Use confident declaratives.
- **Mid-sentence shift**: [whisper] for trailing into quiet. [sigh] for resigned exhale mid-thought.
- **Example**: `I don't know... I thought things would be different by now. I guess I just... hoped for too much.`

### [exhausted]
- **Sentence length**: Very short. Fragments dominate. Minimal effort to form complex thoughts.
- **Punctuation**: `...` between phrases (not hesitation - running out of energy). `.` that feels like collapse. No `!`. Minimal `,` because sentences are too short to need them.
- **Structure**: Fragments ("So tired."). Subject-dropping ("Can't do this anymore." not "I can't do this anymore."). Minimal complete sentences.
- **Word patterns**: Monosyllabic preference. Contractions. Repetition from cognitive fatigue ("I just... I just need to rest.").
- **DO NOT**: Use `!`. Use long well-formed sentences. Use energetic vocabulary.
- **Mid-sentence shift**: [sigh] for exhale moments. [whisper] as energy fades completely.
- **Example**: `I'm done... can't keep going. Just... give me a minute. Please.`

### [nervous]
- **Sentence length**: Variable - starts medium, then fragments as anxiety spikes. Run-on sentences when spiraling.
- **Punctuation**: `...` for hesitation ("Well... the thing is..."). `-` for self-correction ("I was going to - I mean, I thought about --"). `,` piling up in anxious run-ons.
- **Structure**: False starts. Self-interruptions. Backtracking ("No wait, that's not what I meant."). Over-qualifying.
- **Word patterns**: Filler words (well, like, I mean, you know). Hedging (sort of, kind of, maybe, I think). Apologetic openings ("Sorry, I just...").
- **Mid-sentence shift**: [gasp] for sudden panic. [inhale] for trying to steady breathing. [whisper] for shrinking.
- **Example**: `Um, so... the thing is, I wasn't sure if - I mean, I thought maybe we could, you know... try a different approach? If that's okay.`

---

## Physical / Vocal Expressions

> Physical tags should almost always be paired with an emotion tag. They describe
> a vocal action, not a feeling. The emotion tag sets the WHY, the physical tag sets the HOW.

### [sigh]
- **Sentence length**: Short to medium post-sigh. The sigh itself is a pause-beat.
- **Punctuation**: `...` immediately after sigh placement to create exhale pause. `.` heavy afterward (resigned). Low-energy punctuation.
- **Structure**: Concessive statement ("Fine, I'll do it.") or resigned observation. Short responses - the sigh carries emotional weight.
- **Word patterns**: "Fine," "alright," "okay" as openers post-sigh.
- **Pair with**: [tired], [sad], [exhausted], [angry] (burned out anger), [frustrated]
- **Example**: `[tired][sigh] ... Alright. Fine. I'll take care of it. Again.`

### [whisper]
- **Sentence length**: Short. Whispers are effortful and intimate.
- **Punctuation**: `...` sparingly for trailing. No `!` (contradicts register). `,` for breath-pacing (whispering needs more breaths).
- **Structure**: Imperative or confiding ("Don't move." / "I need to tell you something."). Brief questions.
- **Word patterns**: Simple vocabulary. Direct. No filler words (too much effort).
- **DO NOT**: Use `!`. Use long complex sentences. Use loud/energetic vocabulary.
- **Pair with**: [gentle], [tender], [sad], [nervous], [warm]
- **Example**: `[gentle][whisper] Hey... come here. I need to tell you something.`

### [chuckle]
- **Sentence length**: Short. Laughter breaks up speech into fragments.
- **Punctuation**: `-` mid-sentence where laugh interrupts ("I can't - okay, that was funny."). Light punctuation overall.
- **Structure**: Incomplete sentences. Restarts. Punchline then reaction.
- **Word patterns**: Interjections ("oh man", "okay okay"). Self-referential ("I'm sorry, I just can't stop.").
- **Pair with**: [happy], [warm], [playful], [sarcastic] (dry laugh)
- **Mid-sentence placement**: At the exact moment something funny is referenced. Before the reaction, not after.
- **Example**: `[playful] You absolutely cannot wear that shirt with those pants - [chuckle] I say this with love.`

### [laughing]
- **Sentence length**: Very short. Speech barely survives through laughter.
- **Punctuation**: `-` interruptions everywhere. Sentence fragments. Restarts with "okay" or "I'm sorry."
- **Structure**: Almost incoherent at peak. Trying to speak but failing. Multiple attempts.
- **Pair with**: [happy], [excited], [nervous] (nervous laughter)
- **Example**: `[happy][laughing] I can't - okay - I'm sorry, the look on your face - I just can't!`

### [gasp]
- **Sentence length**: 1-3 word reaction, then medium follow-up.
- **Punctuation**: `!` on reaction word. `-` if gasp cuts off previous thought. No `...` (gasps are sudden, not trailing).
- **Structure**: Pure exclamatory fragment first, then question or declaration.
- **Word patterns**: "Oh!" / "No!" / "Wait!" as the gasp-word.
- **Pair with**: [surprised], [nervous], [excited]
- **Mid-sentence placement**: Right before the shocking realization.
- **Example**: `[surprised] The test results came back and - [gasp] oh! That can't be right.`

### [inhale]
- **Sentence length**: The inhale is a pre-speech beat. Following speech is medium, deliberate.
- **Punctuation**: `...` before the first word (breath-gathering). `,` heavy as speaker measures words.
- **Structure**: Complete, considered statement follows. The breath signals importance.
- **Word patterns**: "Okay..." or "Right..." as bridge. Often precedes difficult news or decisions.
- **Pair with**: [nervous], [confident] (steadying breath), [calm]
- **Example**: `[nervous][inhale] ... Okay. Here's the thing. I need to tell you something important.`

---

## Controlled Emotions

### [warm] / [gentle] / [tender]
- **Sentence length**: Medium. Not rushed, not dragging. Flowing and complete.
- **Punctuation**: `,` for soft pauses. `...` sparingly for tender trailing. No `!`. Gentle `.` closings.
- **Structure**: Complete sentences. Endearments and reassurances. Questions as invitations ("How are you feeling?"). Second-person ("You did so well.").
- **Word patterns**: Soft vocabulary (gentle, easy, okay, here). Reassuring phrases. No jargon.
- **DO NOT**: Use `!`. Use staccato short sentences. Use sharp or technical language.
- **Mid-sentence shift**: [whisper] for intimate moments. [chuckle] for affectionate humor.
- **Example**: `Hey, it's okay. You don't have to worry about that right now. Just take your time, alright?`

### [calm] / [professional]
- **Sentence length**: Medium to long. Well-formed, grammatically correct.
- **Punctuation**: Standard `.` and `,`. No `!`. No `...`. Dashes only for structured asides.
- **Structure**: Declarative statements. Logical progression. Structured questions.
- **Word patterns**: No filler words. Minimal contractions. Precise vocabulary. No repetition. No hedging.
- **DO NOT**: Use `...`. Use `!`. Use fragments. Use filler words. Use emotional vocabulary.
- **Example**: `The results are consistent with our initial projections. I recommend proceeding with the second phase as planned.`

### [confident]
- **Sentence length**: Medium. Declarative. Neither curt nor rambling.
- **Punctuation**: Strong `.`. Minimal `?`. No `...`. `!` only for genuine emphasis.
- **Structure**: Subject-verb-object. Active voice exclusively. Assertions, not qualifications. "This will work." not "I think this might work."
- **Word patterns**: No hedging (remove "I think," "maybe," "sort of"). Strong verbs. First-person ownership.
- **DO NOT**: Use `...`. Use hedging. Use passive voice. Use filler words.
- **Example**: `I've reviewed the data. The approach is sound, and I stand behind the recommendation. Let's move forward.`

### [sarcastic]
- **Sentence length**: Medium setup + short punchline.
- **Punctuation**: Deadpan `.` (more sarcastic than `!`). `...` before ironic payoff for timing. `,` for drawn-out delivery.
- **Structure**: Setup + subversion. Apparent agreement then contradiction. Rhetorical questions ("Oh, you don't say?"). Flat observations.
- **Word patterns**: Exaggerated positives used negatively ("Oh, wonderful."). "Really" and "sure" as irony markers. Understatement.
- **DO NOT**: Use `!` (kills the deadpan). Use genuine positive language. Use filler/hedging (sarcasm is deliberate).
- **Mid-sentence shift**: [chuckle] for dry laugh. [sigh] for "I can't even be bothered" energy.
- **Example**: `Oh, that's just perfect. No really, I love when everything falls apart at the last minute... truly inspiring.`

### [playful]
- **Sentence length**: Short to medium. Bouncy rhythm. Varied lengths for dynamic energy.
- **Punctuation**: Light `!`. Teasing `?`. `-` for quick asides. `...` for dramatic teasing ("Guess what...").
- **Structure**: Questions, dares, challenges ("Bet you can't."). Conspiratorial framing ("Okay, so here's the thing.").
- **Word patterns**: Informal. Contractions. Hyperbole ("That's literally the best thing ever."). Tag questions ("Right?").
- **Mid-sentence shift**: [chuckle] for breaking into laughter. [whisper] for conspiratorial asides.
- **Example**: `Okay wait - you're not going to believe this. Guess who just showed up? I'll give you a hint... it's not who you think.`

---

## Mid-Sentence Tag Placement Rules

Mid-sentence tags create emotion shifts within a single line. They should be placed at
natural pivot points where the speaker's emotional state genuinely changes.

### Natural Shift Pairs (start tag -> mid-sentence tag)

| Start Emotion | Good Mid-Sentence Shifts | Pivot Word |
|---|---|---|
| [calm] | [surprised], [emphasis], [gasp] | "wait", "but", "actually" |
| [happy] | [chuckle], [warm], [tender] | "and", "because", sentence break |
| [excited] | [gasp], [chuckle], [happy] | "and", "wait", sentence break |
| [angry] | [sigh], [exhausted], [shouting] | "but", "--", sentence break |
| [sad] | [whisper], [sigh], [warm] | "...", "but", "I guess" |
| [nervous] | [gasp], [inhale], [whisper] | "--", "...", "wait" |
| [confident] | [emphasis], [surprised], [pause] | "but", "and", sentence break |
| [sarcastic] | [chuckle], [sigh], [laughing] | "...", "but", sentence break |
| [playful] | [chuckle], [whisper], [excited] | "--", "...", "wait" |
| [warm] | [whisper], [chuckle], [tender] | "...", "and", sentence break |
| [exhausted] | [sigh], [whisper] | "...", sentence break |

### Placement Rules
1. Place mid-tag AFTER the pivot word/punctuation, not before
2. The text after the mid-tag should match that emotion's formatting rules
3. Emotion shifts should feel like genuine emotional progression, not random
4. Physical tags ([sigh], [chuckle], [gasp]) work best as mid-sentence tags
5. Maximum 1 mid-sentence tag per line (keep it clean for training)

---

## Tag Distribution Targets for Training Dataset

| Tags per line | Target % | Purpose |
|---|---|---|
| 1 tag | 35-40% | Clean single-emotion samples for baseline learning |
| 2 tags (both at start) | 35-40% | Emotion + physical pairing (e.g., [happy][chuckle]) |
| 2 tags (one mid-sentence) | 15-20% | Emotion shift training |
| 3 tags | 5-10% | Complex emotional scenes |

---

## Category Definitions

### Category A: Casual & Core Affection (40% of dataset)
Personal, emotional, relational. Conversations between close people.
Primary tags: [happy], [excited], [chuckle], [whisper], [sad], [warm], [gentle], [playful], [tender], [cheerful]

### Category B: Technical & Reporting (30% of dataset)
Professional, analytical, informational. Work and technical contexts.
Primary tags: [analytical], [confident], [pause], [short pause], [emphasis], [clear], [calm], [professional]

### Category C: Heavy Acting & Physical (30% of dataset)
Dramatic, physically expressive, high-contrast emotions.
Primary tags: [sarcastic], [sigh], [inhale], [surprised], [angry], [exhausted], [nervous], [shouting], [laughing], [gasp]
