# Formatting Audit — Guide Compliance Check

## Batch 1-25

### Issues Found

**ID 2** [confident][exhausted]
- Contradictory pairing. Guide doesn't list confident+exhausted compatibility. Exhausted = fragments, no energy; confident = strong declaratives.

**ID 12** [surprised][calm]
- Contradictory pairing. Calm should not pair with surprised in this way.

**ID 13** [confident]
- Tag mismatch: "Bet you can't catch me" is playful teasing language, not confident assertion. Should be [playful].

**ID 25** [playful][whisper]
- Violates whisper rule: no `!` with whisper. Line ends with `!` but has mid-sentence [whisper]. Whisper should pull energy down, not end energetically.

---

## Batch 2 (26-50)

### Issues Found

**ID 31** [gentle][warm]
- Redundant mid-tag: starts with [gentle][warm], then repeats [warm] mid-sentence. Creates tag repetition — should shift to different emotion if mid-sentence tag needed.

**ID 35** [happy][chuckle]
- Energy-paired chuckle (happy + chuckle = high energy pair) but ends with `.`. Guide: energy-paired chuckles should have ~45% `!` rate. Should be `!` here.

**ID 38** [sad][warm][sigh]
- Three tags at start. Violates max 2 tags at start rule. Contains [sad][warm][sigh] — physical tag + two emotions.

**ID 40** [amused][chuckle]
- Amused + chuckle is energy-paired (amused ≈ happy level). Ends with `.` but should have `!` per energy-pair rule (~45% target).

**ID 41** [warm][chuckle]
- Tag field mismatch: shows [warm][chuckle] but text has [warm] at start and [chuckle] mid-sentence. Tag field should only contain [warm] since chuckle is mid-sentence placement.

---

## Batch 3 (51-75)

### Issues Found

**ID 52** [exhausted]
- Tag-content mismatch: "You make ordinary moments feel like little adventures" is warm/happy content, not exhausted. Exhausted should be fragments and low energy.

**ID 54** [tender][whisper]
- Tag field error: shows both at start but [whisper] is mid-sentence. Tag field should only be [tender].

**ID 56** [whisper][happy]
- Contradictory pairing: whisper does not pair with happy per guide. Whisper pairs with gentle, tender, sad, nervous, warm. Also ends with `!` which violates whisper rule (<5% `!`).

**ID 57** [cheerful][excited]
- Unusual punctuation: ends with `?!` (double mark). Could be intentional for surprise but uncommon pattern.

**ID 61** [happy][excited][chuckle]
- Three tags at start: has [happy][excited][chuckle]. Violates max 2 at start rule. Plus chuckle mid-sentence adds complexity.

**ID 62** [exhausted]
- Tag-content mismatch: "You just yawned and it was the tiniest little yawn" is warm/amused, not exhausted.

**ID 63** [warm][tender]
- Tag field error: shows both at start but [tender] is mid-sentence. Tag field should only be [warm].

**ID 65** [playful][whisper]
- Whisper violates no-`!` rule: ends with `!` but whisper portion has `!` energy. Whisper should pull down, not energize.

**ID 70** [gentle][chuckle]
- Tag field error: shows both at start but [chuckle] is mid-sentence. Tag field should only be [gentle].

---

## Batch 4 (76-100)

### Issues Found

**ID 76** [whisper][tender][sigh]
- Three tags at start: violates max 2 rule.

**ID 81** [analytical]
- Tag-content mismatch: "I don't wanna say goodbye... not yet" is sad/reluctant emotion, not analytical. Analytical should be data/structured reasoning.

**ID 90** [nervous][whisper][gasp]
- Three tags at start: violates max 2 rule.

**ID 92** [tender][warm][whisper]
- Three tags at start: violates max 2 rule.

**ID 96** [tense][gasp][inhale]
- Unknown emotion tag [tense] — not in guide. Also three tags at start (violates rule). Tag-content mismatch: "You're the kind of person who makes the world feel a little softer" is warm/tender, not tense.

**ID 97** [gentle][chuckle]
- Punctuation error: "You've got that worried look again come on..." — missing punctuation between "again" and "come on" (needs dash or comma).

---

## Batch 5 (101-125)

### Issues Found

**ID 103** [excited][inhale]
- Punctuation mismatch: ends with `.` but excited should end with `!` (80-90% target). Content has excited energy throughout.

**ID 108** [gentle][chuckle]
- Tag field error: shows both at start but [chuckle] is mid-sentence. Tag field should only be [gentle].

**ID 110** [tender][happy][whisper]
- Three tags at start: violates max 2 rule.

**ID 112** [warm][tender]
- Tag field error: shows both at start but [tender] is mid-sentence. Tag field should only be [warm].

**ID 113** [exhausted]
- Tag-content mismatch: "I'm so glad I found you" is warm/happy, not exhausted.

**ID 114** [exhausted][sigh]
- Tag-content mismatch: farmer's market/honey sticks is casual/warm, not exhausted. Sigh placement doesn't fix the overall content mismatch.

**ID 116** [happy][gentle][chuckle]
- Three tags at start: violates max 2 rule.

**ID 120** [exhausted]
- Tag-content mismatch: "You're doing so much better... watching it happen makes me so happy" is warm/encouraging, not exhausted.

**ID 121** [surprised][gasp]
- Tag field error: shows both at start but [gasp] is mid-sentence. Tag field should only be [surprised].

**ID 122** [tender][whisper]
- Tag field error: shows both at start but [whisper] is mid-sentence. Tag field should only be [tender].

**ID 124** [gentle][whisper][chuckle]
- Three tags at start: violates max 2 rule.

---

## Batch 6 (126-150)

### Issues Found

**ID 126** [warm][gentle][tender]
- Three tags at start: violates max 2 rule. Also has [tender] mid-sentence, so complex triple structure.

**ID 129** [gentle][sigh]
- Questionable pairing: sigh usually pairs with tired/sad/frustrated/angry. [gentle] is too soft for a sigh — sigh implies resignation or fatigue.

**ID 131** [surprised][nervous]
- Tag-content mismatch: "I'll wait as long as you need... no pressure!" is calm/patient, not surprised/nervous.

**ID 134** [nervous][confident][gasp]
- Contradictory at start: nervous + confident are opposing emotions. Three tags at start (violates rule).

**ID 137** [playful][chuckle][excited]
- Three tags at start: violates max 2 rule.

**ID 138** [happy][tender]
- Tag field error: shows both at start but [tender] is mid-sentence. Tag field should only be [happy].

**ID 146** [happy][cheerful][chuckle]
- Three tags at start: violates max 2 rule.

**ID 147** [warm][chuckle]
- Tag field error: shows both at start but [chuckle] is mid-sentence. Tag field should only be [warm].

---

## Key Patterns Observed

### Most Common Issues (Ranked)

1. **Tag field mismatches with mid-sentence tags**: ~15 instances. Mid-sentence tags are placed correctly in text but tag field lists them as if they're at start.
   - Example: ID 108 shows `[gentle][chuckle]` but chuckle is mid-sentence → should be `[gentle]`

2. **Three tags at start**: ~10 instances. Violates max 2 rule.
   - IDs: 38, 61, 76, 90, 92, 110, 116, 124, 126, 134, 137, 146

3. **Tag-content mismatches**: ~8 instances. Tag emotion doesn't match sentence content.
   - ID 52: [exhausted] but "You make ordinary moments feel like little adventures" (warm)
   - ID 62: [exhausted] but "You just yawned" (warm/amused)
   - ID 81: [analytical] but goodbye sadness (should be sad)
   - ID 113, 114, 120: [exhausted] but warm/encouraging content

4. **Wrong punctuation for emotion**: ~4 instances.
   - ID 103: [excited] ends with `.` but should be `!`
   - ID 35, 40: Energy-paired chuckles should have `!`

5. **Contradictory tag pairings**: ~4 instances.
   - ID 2: [confident][exhausted] (contradictory)
   - ID 12: [surprised][calm]
   - ID 56: [whisper][happy] (whisper doesn't pair with happy)
   - ID 134: [nervous][confident]

6. **Unknown emotion tags**: 1 instance.
   - ID 96: [tense] not in guide

7. **Punctuation/grammar errors**: 1 instance.
   - ID 97: Missing punctuation between "again" and "come on"


## Batch 7401-7420 (Lines 7401-7420)

### Issues Found

**ID 7416** [playful][happy][whisper]
- Wrong punctuation for whisper: the [whisper] mid-sentence section ends with `!` ("The answer is obviously yes!"). Guide states whisper should NEVER get `!`.

---

## Batch 7421-7440 (Lines 7421-7440)

### Issues Found

**ID 7430** [gentle][sigh]
- Questionable tag pairing: [sigh] natural pairs per guide are [tired], [exhausted], [sad], [frustrated], [angry]. [gentle] is not listed as a natural pair for sigh.

**ID 7437** [sad][gentle][warm]
- Punctuation: "Grief doesn't follow a schedule, does it." — tag question "does it" should end with `?` not `.`

**ID 7440** [playful][excited]
- Wrong punctuation for emotion: ends with `.` ("I already signed us up for the hardest one naturally."). [excited] lines should end with `!` or `?` per guide — never `.`

---

## Batch 7441-7460 (Lines 7441-7460)

### Issues Found

**ID 7448** [tender][sigh][whisper]
- Questionable tag pairing: [sigh] natural pairs are [tired], [exhausted], [sad], [frustrated], [angry]. [tender] is not listed as a natural pair for sigh.

**ID 7450** [happy][tender]
- Wrong punctuation for emotion: the [tender] mid-sentence section ends with `!` ("sitting inside it right now feels exactly like being seven years old again!"). Guide says warm/gentle/tender should NOT use `!`.

**ID 7453** [warm][sigh][tender]
- Questionable tag pairing: [sigh] natural pairs are [tired], [exhausted], [sad], [frustrated], [angry]. [warm] is not listed as a natural pair for sigh.

---

## Batch 7461-7480 (Lines 7461-7480)

### Issues Found

**ID 7480** [surprised][gasp][happy]
- Tag-content mismatch: [happy] section describes people being fired overnight — "Nobody got a warning, nobody got a meeting, they just... walked in to locked badges and empty desks." This is shocking/disturbing content, not happy.

---

## Batch 7481-7500 (Lines 7481-7500)

### Issues Found

**ID 7488** [shouting][sigh]
- Contradictory tag context: [sigh] mid-sentence during emergency evacuation ("the fire alarm isn't a drill, I can actually smell smoke"). Sigh = resignation/fatigue, which contradicts urgent emergency shouting context.

---

## Batch 7501-7520 (Lines 7501-7520)

### Issues Found

**ID 7501** [happy][laughing][tender]
- Tag-content mismatch: [tender] section is "I don't know what's happening anymore at this company." This is confused/amused, not tender (intimacy, vulnerability, affection).

**ID 7510** [sad][whisper][warm]
- Tag-content mismatch: [warm] section is "It's not about anything specific, just a heaviness that showed up uninvited and stayed." Content describes sadness/heaviness, not warmth or comfort.

---

## Batch 7521-7540 (Lines 7521-7540)

### Issues Found

No issues found. Lines 7526-7540 are untagged neutral baseline lines — structurally correct with proper punctuation and neutral content.

---

## Batch 7541-7560 (Lines 7541-7560)

### Issues Found

No issues found. All untagged neutral baseline lines with proper structure.

---

## Batch 7561-7580 (Lines 7561-7580)

### Issues Found

No issues found. All untagged neutral baseline lines with proper structure.

---

## Batch 7581-7600 (Lines 7581-7600)

### Issues Found

No issues found. All untagged neutral baseline lines with proper structure.

---

## Batch 7601-7625 (Lines 7601-7625)

### Issues Found

No issues found. All untagged neutral baseline lines with proper structure.

---

## Batch 6661-6680 (Lines 6661-6680)

### Issues Found

**ID 6663** [excited][happy][chuckle]
- Three tags at start: text begins `[excited][happy]` (2 at start), then `[chuckle]` mid-sentence. Tag field lists all three concatenated as `[excited][happy][chuckle]`, which is correct. No issue on re-check -- mid-sentence chuckle is valid.

**ID 6671** [cheerful][chuckle][excited]
- Tag field `[cheerful][chuckle][excited]` lists 3 tags. Text starts `[cheerful][chuckle]` (2 at start), then `[excited]` mid-sentence. Tag field is correct. No issue.

**ID 6675** [happy][tender]
- Wrong punctuation for emotion: the `[tender]` mid-sentence section ends with `!` ("The world feels enormous and full of possibility in that instant!"). Guide says tender should NOT use `!`.

---

## Batch 6681-6700 (Lines 6681-6700)

### Issues Found

**ID 6690** [gentle][calm][chuckle]
- Three tags at start: text begins `[gentle][calm]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No start-rule violation.

**ID 6691** [playful][chuckle][whisper]
- Three tags at start: text begins `[playful][chuckle]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No start-rule violation.

**ID 6694** [tender][whisper][chuckle]
- Three tags at start: text begins `[tender][whisper]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No start-rule violation.

No issues found in this batch.

---

## Batch 6701-6720 (Lines 6701-6720)

### Issues Found

**ID 6708** [gentle][warm][whisper]
- Three tags at start: text begins `[gentle][warm]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

**ID 6715** [excited][chuckle][happy]
- Three tags at start: text begins `[excited][chuckle]` (2 at start), `[happy]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6721-6740 (Lines 6721-6740)

### Issues Found

**ID 6723** [calm][sigh]
- Questionable tag pairing: [sigh] natural pairs per guide are [tired], [exhausted], [sad], [frustrated], [angry]. [calm] is not listed as a natural pair for sigh.

**ID 6726** [happy][tender]
- Wrong punctuation for emotion: the `[tender]` section ends with `!` ("Revolutionary breakfast content right here!"). Guide says tender should NOT use `!`.

---

## Batch 6741-6760 (Lines 6741-6760)

### Issues Found

No issues found. Lines are structurally sound with correct tag placement and punctuation matching emotion.

---

## Batch 6761-6780 (Lines 6761-6780)

### Issues Found

**ID 6776** [warm][whisper][chuckle]
- Tag field `[warm][whisper][chuckle]` lists 3 tags. Text starts `[warm][whisper]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 6777** [cheerful][happy][excited]
- Three tags at start: text begins `[cheerful][happy]` (2 at start), `[excited]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6781-6800 (Lines 6781-6800)

### Issues Found

**ID 6781** [calm][gentle][surprised]
- Three tags at start: text begins `[calm][gentle]` (2 at start), `[surprised]` is mid-sentence. Tag field correct. No violation.

**ID 6789** [happy][chuckle]
- Tag placement: `[chuckle]` appears mid-sentence ("and [chuckle] even though...") but tag field lists `[happy][chuckle]` as if both are at start. However, examining text: `[happy] I spent...and [chuckle] even though...` -- both tags are correctly represented in the tag field, and mid-sentence placement is correct. Tag field should include all tags regardless of position per the guide rule. No violation.

**ID 6797** [calm][warm][surprised]
- Three tags at start: text begins `[calm][warm]` (2 at start), `[surprised]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6801-6820 (Lines 6801-6820)

### Issues Found

**ID 6812** [playful][gasp]
- Tag-content mismatch (minor): "This is a betrayal." -- the word "betrayal" sounds angry but the context is clearly playful mock-outrage about a sourdough starter named Barbara. Arguably fine given the humorous tone.

**ID 6820** [calm][gasp]
- Questionable tag pairing: [gasp] natural pairs per guide are [surprised], [nervous], [excited]. [calm] is not listed as a natural pair for gasp. Also, the [gasp] section content ("The water doesn't fight the obstacles...") is still philosophical and calm in tone -- not a sudden shocked reaction. The gasp doesn't fit the meditative content.

---

## Batch 6821-6840 (Lines 6821-6840)

### Issues Found

No issues found. Lines are structurally sound.

---

## Batch 6841-6860 (Lines 6841-6860)

### Issues Found

**ID 6855** [cheerful][gasp][excited]
- Three tags at start: text begins `[cheerful][gasp]` (2 at start), `[excited]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6861-6880 (Lines 6861-6880)

### Issues Found

**ID 6861** [gentle][whisper][warm]
- Three tags at start: text begins `[gentle][whisper]` (2 at start), `[warm]` is mid-sentence. Tag field correct. No violation.

**ID 6876** [tender][calm][chuckle]
- Three tags at start: text begins `[tender][calm]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6881-6900 (Lines 6881-6900)

### Issues Found

**ID 6892** [cheerful][chuckle][excited]
- Three tags at start: text begins `[cheerful][chuckle]` (2 at start), `[excited]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6901-6920 (Lines 6901-6920)

### Issues Found

**ID 6912** [excited][chuckle][gasp]
- Three tags at start: text begins `[excited][chuckle]` (2 at start), `[gasp]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6921-6940 (Lines 6921-6940)

### Issues Found

**ID 6922** [cheerful][happy][chuckle]
- Three tags at start: text begins `[cheerful][happy]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 6923** [calm][warm][emphasis]
- Three tags at start: text begins `[calm][warm]` (2 at start), `[emphasis]` is mid-sentence. Tag field correct. No violation.

**ID 6934** [gentle][calm][warm]
- Three tags at start: text begins `[gentle][calm]` (2 at start), `[warm]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6941-6960 (Lines 6941-6960)

### Issues Found

**ID 6946** [cheerful][chuckle][happy]
- Three tags at start: text begins `[cheerful][chuckle]` (2 at start), `[happy]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 6961-6980 (Lines 6961-6980)

### Issues Found

**ID 6969** [gentle][sigh][chuckle]
- Text: "Great stories don't just end... they linger, echoing through your thoughts for days." -- the `...` here is fine for gentle (under 8% threshold).

No issues found in this batch.

---

## Batch 6981-7000 (Lines 6981-7000)

### Issues Found

**ID 6990** [tender][warm][chuckle]
- Three tags at start: text begins `[tender][warm]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 6997** [gentle][inhale][chuckle]
- Three tags at start: text begins `[gentle][inhale]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7001-7020 (Lines 7001-7020)

### Issues Found

**ID 7006** [gentle][calm][whisper]
- Three tags at start: text begins `[gentle][calm]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

**ID 7014** [cheerful][warm][chuckle]
- Three tags at start: text begins `[cheerful][warm]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 7019** [excited][happy][chuckle]
- Three tags at start: text begins `[excited][happy]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7021-7040 (Lines 7021-7040)

### Issues Found

**ID 7021** [calm][gasp]
- Questionable tag pairing: [gasp] natural pairs per guide are [surprised], [nervous], [excited]. [calm] is not listed as a natural pair for gasp. The [gasp] section content ("You cannot rush fermentation.") is still meditative/calm, not a sudden shock reaction. Gasp doesn't fit the philosophical content.

No other issues found in this batch.

---

## Batch 7041-7060 (Lines 7041-7060)

### Issues Found

**ID 7041** [warm][confident][tender]
- Three tags at start: text begins `[warm][confident]` (2 at start), `[tender]` is mid-sentence. Tag field correct. No violation.

**ID 7046** [cheerful][chuckle][excited]
- Three tags at start: text begins `[cheerful][chuckle]` (2 at start), `[excited]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7061-7080 (Lines 7061-7080)

### Issues Found

**ID 7074** [cheerful][chuckle][excited]
- Three tags at start: text begins `[cheerful][chuckle]` (2 at start), `[excited]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7081-7100 (Lines 7081-7100)

### Issues Found

**ID 7097** [whisper][tender][sigh]
- Three tags at start: text begins `[whisper][tender]` (2 at start), `[sigh]` is mid-sentence. Tag field correct. No start-rule violation.
- Questionable tag pairing: [sigh] natural pairs are [tired], [exhausted], [sad], [frustrated], [angry]. [tender] is not listed as a natural pair for sigh. However, the content ("nothing else in the world exists") is peaceful/intimate -- sigh here reads as contentment rather than resignation, which stretches the guide's definition.

No other issues found in this batch.

---

## Batch 7101-7120 (Lines 7101-7120)

### Issues Found

**ID 7109** [gentle][whisper][chuckle]
- Three tags at start: text begins `[gentle][whisper]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7121-7140 (Lines 7121-7140)

### Issues Found

**ID 7131** [playful][chuckle][excited]
- Three tags at start: text begins `[playful][chuckle]` (2 at start), `[excited]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7141-7160 (Lines 7141-7160)

### Issues Found

No issues found in this batch.

---

## Batch 7161-7180 (Lines 7161-7180)

### Issues Found

No issues found in this batch.

---

## Batch 7181-7200 (Lines 7181-7200)

### Issues Found

**ID 7193** [gentle][whisper][chuckle]
- Three tags at start: text begins `[gentle][whisper]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7201-7220 (Lines 7201-7220)

### Issues Found

No issues found in this batch.

---

## Batch 7221-7240 (Lines 7221-7240)

### Issues Found

**ID 7221** [playful][chuckle][whisper]
- Three tags at start: text begins `[playful][chuckle]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

**ID 7235** [cheerful][chuckle][excited]
- Three tags at start: text begins `[cheerful][chuckle]` but wait -- text is `[cheerful][chuckle] Our matching mugs arrived...` then `[excited] Mine says sunrise...`. So 2 at start, 1 mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7241-7260 (Lines 7241-7260)

### Issues Found

**ID 7246** [cheerful][warm][happy]
- Three tags at start: text begins `[cheerful][warm]` (2 at start), `[happy]` is mid-sentence. Tag field correct. No violation.

**ID 7250** [excited][happy][chuckle]
- Three tags at start: text begins `[excited][happy]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 7252** [tender][whisper][chuckle]
- Three tags at start: text begins `[tender][whisper]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 7256** [sad][whisper][sigh]
- Three tags at start: text begins `[sad][whisper]` (2 at start), `[sigh]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7261-7280 (Lines 7261-7280)

### Issues Found

**ID 7266** [happy][excited][chuckle]
- Three tags at start: text begins `[happy][excited]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 7279** [tender][gentle][whisper]
- Three tags at start: text begins `[tender][gentle]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7281-7300 (Lines 7281-7300)

### Issues Found

**ID 7281** [warm][tender][whisper]
- Three tags at start: text begins `[warm][tender]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

**ID 7294** [warm][gentle][chuckle]
- Three tags at start: text begins `[warm][gentle]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

**ID 7298** [sad][gentle][sigh]
- Three tags at start: text begins `[sad][gentle]` (2 at start), `[sigh]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7301-7320 (Lines 7301-7320)

### Issues Found

**ID 7303** [happy][warm][tender]
- Three tags at start: text begins `[happy][warm]` (2 at start), `[tender]` is mid-sentence. Tag field correct. No violation.

**ID 7308** [whisper][gentle][sigh]
- Three tags at start: text begins `[whisper][gentle]` (2 at start), `[sigh]` is mid-sentence. Tag field correct. No violation.
- Questionable tag pairing: [sigh] natural pairs are [tired], [exhausted], [sad], [frustrated], [angry]. [gentle] is not listed as a natural pair for sigh.

**ID 7319** [happy][tender][warm]
- Three tags at start: text begins `[happy][tender]` (2 at start), `[warm]` is mid-sentence. Tag field correct. No violation.

**ID 7321** [cheerful][warm][chuckle]
- Three tags at start: text begins `[cheerful][warm]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7321-7340 (Lines 7321-7340)

### Issues Found

**ID 7328** [excited][happy][chuckle]
- Three tags at start: text begins `[excited][happy]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7341-7360 (Lines 7341-7360)

### Issues Found

**ID 7347** [tender][warm][whisper]
- Three tags at start: text begins `[tender][warm]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

**ID 7352** [whisper][tender][sigh]
- Three tags at start: text begins `[whisper][tender]` (2 at start), `[sigh]` is mid-sentence. Tag field correct. No violation.
- Questionable tag pairing: [sigh] natural pairs are [tired], [exhausted], [sad], [frustrated], [angry]. [tender] is not listed as a natural pair for sigh. Content is wistful/dreamy, and sigh here reads as longing rather than resignation.

**ID 7354** [gentle][warm][chuckle]
- Three tags at start: text begins `[gentle][warm]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7361-7380 (Lines 7361-7380)

### Issues Found

**ID 7367** [warm][tender][whisper]
- Three tags at start: text begins `[warm][tender]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

**ID 7375** [warm][happy]
- Punctuation: ends with `!` ("that's exactly the kind of person I just want to build a life with!"). The [warm] start tag would normally not use `!`, but the [happy] mid-sentence shift brings `!`-appropriate energy. Borderline -- `!` is driven by [happy] not [warm]. Acceptable.

**ID 7377** [tender][warm][whisper]
- Three tags at start: text begins `[tender][warm]` (2 at start), `[whisper]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Batch 7381-7400 (Lines 7381-7400)

### Issues Found

**ID 7392** [warm][whisper][tender]
- Three tags at start: text begins `[warm][whisper]` (2 at start), `[tender]` is mid-sentence. Tag field correct. No violation.

**ID 7397** [cheerful][warm][chuckle]
- Three tags at start: text begins `[cheerful][warm]` (2 at start), `[chuckle]` is mid-sentence. Tag field correct. No violation.

No issues found in this batch.

---

## Summary: Lines 6661-7400

### Confirmed Issues

1. **Wrong punctuation for emotion**: 2 instances
   - ID 6675: [tender] mid-sentence section ends with `!` -- guide says tender should NOT use `!`
   - ID 6726: [tender] section ends with `!` -- same violation

2. **Questionable tag pairings**: 4 instances
   - ID 6723: [calm][sigh] -- sigh does not naturally pair with calm per guide
   - ID 6820: [calm][gasp] -- gasp does not naturally pair with calm; content is meditative, not shocked
   - ID 7021: [calm][gasp] -- same issue as 6820; philosophical content with gasp tag
   - ID 7097: [whisper][tender][sigh] -- sigh does not naturally pair with tender
   - ID 7308: [whisper][gentle][sigh] -- sigh does not naturally pair with gentle
   - ID 7352: [whisper][tender][sigh] -- sigh does not naturally pair with tender

### Observations

This range (6661-7400) is notably clean compared to earlier batches (1-150). The 740 lines are almost entirely Category A casual/affection content with well-structured tag fields, proper mid-sentence tag placement, and correct punctuation-emotion alignment. The most common pattern is 3-tag lines with 2 at start + 1 mid-sentence, all correctly handled. No tag field mismatches, no unknown tags, no three-tags-at-start violations, and no contradictory pairings were found. The only real issues are two tender+`!` punctuation violations and a handful of sigh/gasp paired with emotions outside their natural partner list.

---

