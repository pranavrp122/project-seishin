# Archie's 10-Hour Voice Master Plan — Implementation Blueprint

## Context

**Problem**: Build a complete automated pipeline to generate a 7,500-sample synthetic TTS dataset that captures a specific voice identity from a seed MP4, generates diverse tagged text prompts via the Anthropic API, and synthesizes all audio locally using Fish Audio S2 Pro. The dataset will later be used to LoRA fine-tune S2 Pro for deployment as a replacement for Qwen3-TTS in the Nexus Engine's seishin-mouth daemon.

**What prompted this**: The current Qwen3-TTS 1.7B in seishin-mouth lacks fine-grained emotion/tag control. Fish S2 Pro (4B params) natively supports 15,000+ inline `[tag]` directives, making it the ideal base for a LoRA-tuned voice model that responds to semantic emotion tags.

**Intended outcome**: A production-ready dataset at `dataset_pipeline/audio/` containing 7,500 `.wav` + `.lab` pairs, ready for VQ extraction and LoRA training.

---

## Execution Strategy

### Parallel Subagents
Spawn subagents for independent work streams wherever possible. Key parallelization points:
- **Phase 0**: Install ffmpeg + Install Fish Speech deps + Install anthropic SDK (3 parallel agents)
- **Phase 1**: Extract audio + Create directory structure (2 parallel agents)
- **Phase 2-3**: Test batch generation and script generation are sequential (depend on prior phases)
- **Phase 4**: Factory loop is single-threaded (Fish S2 Pro API is single-worker)

### Shared Task Coordination
- Task tracking via `dataset_pipeline/tasks/` folder
- Each subagent reads current task state and updates on completion
- Provides visibility into pipeline progress across agents

### CLAUDE.md Updates
Update `/home/prana/project-seishin/CLAUDE.md` incrementally as new infrastructure is established (dataset pipeline paths, Fish S2 Pro server details, training pipeline commands).

### Hands-Off Existing Scripts
**DO NOT modify**: `ears_daemon.py`, `mouth_daemon.py`, `nexus_engine.py`, `system_prompts.py`, or any files under `scripts/`. These are working production code. The mouth daemon migration (Phase 6) is a separate future task.

---

## Phase 0: Prerequisites

### 0A. Install ffmpeg on WSL host
```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

### 0B. Install Fish Speech dependencies
```bash
cd /home/prana/fish-speech
uv sync --extra cu126
```
- The venv at `fish_env/` currently has only torch — this installs all 30+ missing deps (transformers, ormsgpack, hydra, librosa, etc.)
- If torch version conflict (pyproject pins 2.8.0, venv has 2.11.0+cu126): edit `pyproject.toml` to pin `torch==2.11.0` and run `uv lock --extra cu126` first

Verify:
```bash
/home/prana/fish-speech/fish_env/bin/python -c "from fish_speech.utils.schema import ServeTTSRequest; print('OK')"
```

### 0C. Download S2 Pro model checkpoints
```bash
cd /home/prana/fish-speech
mkdir -p checkpoints
/home/prana/fish-speech/fish_env/bin/python -m huggingface_hub download fishaudio/openaudio-s2-pro \
  --local-dir checkpoints/s2-pro
```
- Expected: `model.pth`, `config.json`, `tokenizer.tiktoken`, `codec.pth`
- Requires HF_TOKEN if model is gated (check `.env` for existing token)
- `api_utils.py:27-28` already defaults to `checkpoints/s2-pro` — no code change needed

### 0D. Update API_FLAGS.txt
**File**: `/home/prana/fish-speech/API_FLAGS.txt`

Change from `openaudio-s1-mini` to:
```
--api
--listen 0.0.0.0:8080 \
--llama-checkpoint-path "checkpoints/s2-pro" \
--decoder-checkpoint-path "checkpoints/s2-pro/codec.pth" \
--decoder-config-name modded_dac_vq
```

### 0E. Install Anthropic SDK (host Python)
```bash
pip install anthropic
```
- Add `ANTHROPIC_API_KEY` to `/home/prana/project-seishin/.env` (gitignored per Scrubber protocol)
- Load in shell: `export $(grep ANTHROPIC_API_KEY .env | xargs)`

---

## Phase 1: Seed Preparation

### 1A. Create directory structure
```
dataset_pipeline/
    master_seed.wav       # Reference audio
    master_seed.txt       # Reference transcript (USER MUST PROVIDE)
    test_batch.json       # 9 test sentences
    master_script.jsonl   # 7,500 Claude-generated sentences
    test_audio/           # 9 test outputs
    audio/                # 7,500 production outputs (NNNN.wav + NNNN.lab)
```

### 1B. Extract audio from MP4
```bash
ffmpeg -i "/home/prana/project-seishin/Untitled Project.mp4" \
  -vn -acodec pcm_s16le -ar 44100 -ac 1 \
  /home/prana/project-seishin/dataset_pipeline/master_seed.wav
```
- **44100 Hz** is critical — matches Fish S2 Pro's DAC codec native rate (`modded_dac_vq.yaml:3`)
- Mono PCM 16-bit for maximum compatibility

### 1C. Reference transcript
Save to `dataset_pipeline/master_seed.txt`:
```
To be able to hear a vague prophecy in my dreams and move forward under its guidance... I think that's pretty magical, too. As it turns out, it was never a miracle granted by someone else, but the self deep within my own heart. When I have trouble sleeping, I count the stars in the sky and imagine a shooting star flying across the night and diving into my dreams. Then I wake up with a smile and start a bright new day... because I know it wasn't a dream. Thirty million similar yet different stories... Doesn't it sound like a lot? But I never grew tired of it. I even relived it when I travelled with you, and it was still so moving! However, there were always regrets left on every single page. I wanted to add some smiles here and fill up some blanks there... It was all thanks to you that we could finally compose a romantic ending for them.
```

---

## Phase 2: Test Batch (9 Samples) — APPROVAL GATE

### 2A. Create `dataset_pipeline/test_batch.json`
9 sentences — 3 per category, demonstrating:
- Natural ellipses for pacing (`...`)
- Max 2 tags per sentence
- Mix of 1-tag and 2-tag sentences
- Physical cues (`[sigh]`, `[chuckle]`) placed mid-thought

**Category A** (Casual & Core Affection):
```json
{"tag": "[warm]", "text": "[warm] Hey... I was just thinking about you. How's your day going?"}
{"tag": "[excited][chuckle]", "text": "[excited][chuckle] Oh my god, you actually did it! I knew you could."}
{"tag": "[gentle][whisper]", "text": "[gentle][whisper] I'm right here... you don't have to worry about anything."}
```

**Category B** (Technical & Reporting):
```json
{"tag": "[clear]", "text": "[clear] The latency metrics show a twelve percent improvement after the cache optimization."}
{"tag": "[analytical]", "text": "[analytical] Based on the data... we should prioritize the memory allocation issue first."}
{"tag": "[confident][emphasis]", "text": "[confident][emphasis] All integration tests passed. The deployment pipeline is stable."}
```

**Category C** (Heavy Acting & Physical):
```json
{"tag": "[sigh][tired]", "text": "[sigh][tired] I've been staring at this for hours... my eyes are killing me."}
{"tag": "[excited]", "text": "[excited] Wait wait wait — are you serious?! That's incredible!"}
{"tag": "[angry]", "text": "[angry] No. I told you three times already, that's not how it works."}
```

### 2B. Create `dataset_pipeline/test_generate.py`
- **Interpreter**: `/home/prana/fish-speech/fish_env/bin/python` (needs ormsgpack, fish_speech.utils.schema)
- Reads `test_batch.json`, `master_seed.wav`, `master_seed.txt`
- POSTs to Fish S2 Pro API at `http://127.0.0.1:8080/v1/tts`
- Uses `ServeTTSRequest` with `use_memory_cache="on"` to cache reference encoding
- Saves 9 WAVs to `dataset_pipeline/test_audio/`
- API call pattern follows `/home/prana/fish-speech/tools/api_client.py:161-196` (ormsgpack + msgpack content type)

### 2C. Run test generation
**Pre-requisite**: Stop all 3 Docker containers, start Fish S2 Pro API server:
```bash
docker stop seishin-ears seishin-brain seishin-mouth
cd /home/prana/fish-speech
/home/prana/fish-speech/fish_env/bin/python tools/api_server.py \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --decoder-config-name modded_dac_vq \
  --listen 127.0.0.1:8080
```

**STOP HERE** — User listens to 9 test audio files and approves quality before proceeding.

---

## Phase 3: Claude Dataset Generation — `generate_script.py`

### 3A. Script location and interpreter
- **File**: `/home/prana/project-seishin/dataset_pipeline/generate_script.py`
- **Interpreter**: Host Python 3.12 (only needs `anthropic` package, no fish_speech deps)

### 3B. Model progression strategy
| Phase | Model | Thinking | Count | Purpose |
|---|---|---|---|---|
| Seed | `claude-opus-4-6` | Extended (max budget) | 200/category (600 total) | Establish high-quality variance |
| Bulk | `claude-sonnet-4-6` | Standard | Remaining (6,900 total) | Rapid generation matching seed patterns |

### 3C. Category distribution (7,500 total)
| Cat | Name | Count | Tags Pool |
|---|---|---|---|
| A | Casual & Core Affection | 3,000 (40%) | `[happy]`, `[excited]`, `[chuckle]`, `[whisper]`, `[sad]`, `[warm]`, `[gentle]`, `[playful]`, `[tender]`, `[cheerful]` |
| B | Technical & Reporting | 2,250 (30%) | `[analytical]`, `[confident]`, `[pause]`, `[short pause]`, `[emphasis]`, `[clear]`, `[calm]`, `[professional]` |
| C | Heavy Acting & Physical | 2,250 (30%) | `[sarcastic]`, `[sigh]`, `[inhale]`, `[surprised]`, `[angry]`, `[exhausted]`, `[nervous]`, `[shouting]`, `[laughing]`, `[gasp]` |

### 3C-ii. Duration variation (applied across ALL categories)
| Length | Word Count | ~Duration | Share | Count |
|---|---|---|---|---|
| Short | 5-15 words | 3-6s | 40% | 3,000 |
| Medium | 15-35 words | 6-12s | 40% | 3,000 |
| Long | 35-60 words | 12-15s | 20% | 1,500 |

Each Claude API batch request specifies a target word count range. This distribution applies proportionally within each category (e.g., Category A: 1,200 short + 1,200 medium + 600 long = 3,000). Varied length teaches the model natural pacing across quick replies, conversational exchanges, and longer monologues.

### 3D. Prompt styling rules (enforced in system prompt to Claude)
1. **Max 2 tags per sentence** — healthy mix of 1-tag (~60%) and 2-tag (~40%)
2. **Tag format**: Each tag gets its OWN brackets: `[happy][tired]` NOT `[happy, tired]`
3. **Tag placement**:
   - Start of sentence for whole-sentence emotion: `[warm] Hey, how are you doing?`
   - Both at start for dual-emotion: `[happy][excited] Oh my god, that's amazing!`
   - Second tag mid-sentence for emotion SHIFT (use sparingly, ~15% of 2-tag sentences): `[calm] The results look fine... [surprised] wait, what is that spike?`
   - Keep mid-sentence shifts realistic — don't overdo it
4. **Ellipses** (`...`) for organic micro-pauses and trailing thoughts
5. **Physical tags** (`[sigh]`, `[chuckle]`, `[inhale]`) can appear at start or mid-sentence
6. **No quotation marks** wrapping the sentence
7. **Varied sentence length**: 5-40 words

### 3E. Output format
`dataset_pipeline/master_script.jsonl` — one JSON per line:
```jsonl
{"id": 1, "category": "A", "tag": "[warm]", "text": "[warm] Hey... I was just thinking about you."}
{"id": 2, "category": "A", "tag": "[excited][chuckle]", "text": "[excited][chuckle] Oh my god, that's amazing!"}
{"id": 3, "category": "C", "tag": "[calm]", "text": "[calm] The results look fine... [surprised] wait, what is that spike?"}
```

### 3F. Resumability
- On startup, reads existing JSONL and counts sentences per category
- Skips categories that are already complete
- Generates in batches of 50 sentences per API call
- Appends to JSONL after each successful batch

### 3G. Scrubber compliance
- `ANTHROPIC_API_KEY` loaded from `.env` via `os.environ`, never hardcoded
- No API key values logged or printed
- `.env` is gitignored

---

## Phase 4: Factory Loop — `factory_loop.py`

### 4A. Script location and interpreter
- **File**: `/home/prana/project-seishin/dataset_pipeline/factory_loop.py`
- **Interpreter**: `/home/prana/fish-speech/fish_env/bin/python` (needs ormsgpack + fish_speech.utils.schema for API calls)

### 4B. Tag translation matrix
```python
TAG_TRANSLATIONS = {
    "[sarcastic]": "[deadpan][sarcastic][low pitch]",
    "[analytical]": "[clear][articulate][slow]",
}
# All other tags pass through unchanged to Fish S2 Pro's native handler
```
- Only `[sarcastic]` and `[analytical]` get custom expansion per user spec
- Expanded tags use individual bracket format: `[deadpan][sarcastic][low pitch]`
- All other tags (`[happy]`, `[angry]`, `[pause]`, `[sigh]`, etc.) pass directly — Fish S2 Pro supports them natively

### 4C. Core loop
```
for each line in master_script.jsonl:
  1. Check if audio/NNNN.wav exists → skip (resume support)
  2. Apply TAG_TRANSLATIONS to text
  3. POST ServeTTSRequest to http://127.0.0.1:8080/v1/tts
     - references: [ServeReferenceAudio(audio=master_seed_bytes, text=master_seed_text)]
     - use_memory_cache: "on" (caches reference encoding after first call)
     - format: "wav"
  4. Save response as audio/NNNN.wav
  5. Save ORIGINAL text (pre-translation, with original tags) as audio/NNNN.lab
```

### 4D. .lab file content (CRITICAL)
The `.lab` file contains the **original tag formulation** from the JSONL, NOT the translated version:
- JSONL: `{"tag": "[sarcastic]", "text": "[sarcastic] Oh great, another bug."}`
- Sent to S2 Pro: `[deadpan, sarcastic, low pitch] Oh great, another bug.`
- Saved to 0001.lab: `[sarcastic] Oh great, another bug.`

This preserves the simple tag vocabulary for LoRA training.

### 4E. Error handling
- 3 retries with exponential backoff (2s, 4s, 8s) on HTTP 500/503
- Skip and log on persistent failure (don't block the pipeline)
- 120s timeout per request
- Progress logged every 100 samples with ETA
- Crash recovery: restart script, skip existing files

### 4F. Timing estimate
- Per-sample: ~3-8 seconds generation (varies with text length; 4B model on RTX 5090 with 32GB exclusive)
- With varied duration (avg ~9s audio per sample): **~10-14 hours** for 7,500 samples
- Reference encoding cached after first call (negligible amortized cost)
- Overnight run recommended — start before bed, check progress in morning

### 4G. Pre-launch checklist
1. `docker stop seishin-ears seishin-brain seishin-mouth`
2. `nvidia-smi` → verify ~0 MB used
3. Start Fish S2 Pro API server (terminal 1)
4. `curl http://127.0.0.1:8080/v1/health` → `{"status": "ok"}`
5. Start factory_loop.py (terminal 2)
6. Monitor: `watch -n 60 'ls dataset_pipeline/audio/*.wav | wc -l'`

**STOP** after factory loop completes. User approves dataset before Phase 5.

---

## Phase 5: Training & Deployment Prep

### 5A. Extract VQ tokens (~5 min)
```bash
cd /home/prana/fish-speech
/home/prana/fish-speech/fish_env/bin/python tools/vqgan/extract_vq.py \
  /home/prana/project-seishin/dataset_pipeline/audio/ \
  --checkpoint-path checkpoints/s2-pro/codec.pth \
  --config-name modded_dac_vq \
  --batch-size 64
```
- Reads each `.wav`, encodes through DAC codec, saves `.npy` alongside
- Skips files that already have `.npy` (built-in resume)
- `build_dataset.py`'s text cleaning (lines 79-82) strips `{...}` and `<...>` but NOT `[...]` — our tags survive into training data

### 5B. Build protobuf dataset (~2 min)
```bash
/home/prana/fish-speech/fish_env/bin/python tools/llama/build_dataset.py \
  --input /home/prana/project-seishin/dataset_pipeline/audio/ \
  --output data/quantized-dataset-ft \
  --text-extension .lab \
  --num-workers 4
```

### 5C. LoRA fine-tuning (~2-4 hours)

Modify `/home/prana/fish-speech/fish_speech/configs/text2semantic_finetune.yaml`:
- `pretrained_ckpt_path: checkpoints/s2-pro`
- `train_dataset.proto_files: [data/quantized-dataset-ft]`
- `val_dataset.proto_files: [data/quantized-dataset-ft]`

```bash
/home/prana/fish-speech/fish_env/bin/python fish_speech/train.py \
  --config-name text2semantic_finetune \
  trainer.max_steps=10000 \
  model.model.lora_config=r_8_alpha_16
```
- Uses LoRA config `r_8_alpha_16.yaml` (r=8, alpha=16, dropout=0.01)
- BF16 precision on RTX 5090
- Checkpoints saved every 100 steps to `results/text2semantic_finetune_dual_ar/checkpoints/`

### 5D. Merge LoRA adapters
```bash
/home/prana/fish-speech/fish_env/bin/python tools/llama/merge_lora.py \
  --lora-config r_8_alpha_16 \
  --base-weight checkpoints/s2-pro \
  --lora-weight results/text2semantic_finetune_dual_ar/checkpoints/step_000010000.ckpt \
  --output checkpoints/s2-pro-finetuned
```

### 5E. Quantization decision
**Keep BF16 for now.** Rationale:
- S2 Pro 4B at BF16 = ~8 GB. DAC codec = ~2 GB. Total ~10 GB.
- RTX 5090 has 32 GB — comfortable even alongside other containers
- Fish Speech's `quantize.py` supports int4/int8 only, NOT FP8
- If VRAM tight when running with brain+ears: use int8 via `tools/llama/quantize.py`
- vLLM FP8 serving NOT viable — S2 Pro uses custom DualARTransformer, not standard LLM arch

### 5F. Deployment to seishin-mouth (separate future task)
Rewriting `mouth_daemon.py` to use Fish S2 Pro instead of Qwen3-TTS is a **separate task** — not part of this pipeline execution. Key changes needed:
- Replace `qwen3-tts-triton` runner with Fish S2 Pro API calls
- Map `(emotion)` prefix from LLM → Fish S2 Pro `[tag]` format
- Resample 44100 Hz → 48000 Hz (new FIR filter, different from current 24kHz→48kHz)
- VRAM budget: ~10 GB (S2 Pro BF16) vs current ~4.3 GB (Qwen3-TTS) — fits within 32 GB total

---

## Critical Files Reference

| File | Role |
|---|---|
| `/home/prana/fish-speech/tools/api_client.py` | Reference implementation for API call pattern |
| `/home/prana/fish-speech/fish_speech/utils/schema.py` | `ServeTTSRequest` + `ServeReferenceAudio` data models |
| `/home/prana/fish-speech/tools/api_server.py` | API server entry point |
| `/home/prana/fish-speech/tools/server/api_utils.py:27-28` | Default checkpoint paths (already S2 Pro) |
| `/home/prana/fish-speech/fish_speech/configs/modded_dac_vq.yaml` | DAC codec config (44100 Hz sample rate) |
| `/home/prana/fish-speech/fish_speech/configs/text2semantic_finetune.yaml` | Training config (needs S2 Pro path update) |
| `/home/prana/fish-speech/fish_speech/configs/lora/r_8_alpha_16.yaml` | LoRA config for fine-tuning |
| `/home/prana/fish-speech/tools/vqgan/extract_vq.py` | VQ token extraction |
| `/home/prana/fish-speech/tools/llama/build_dataset.py` | Protobuf dataset builder |
| `/home/prana/fish-speech/tools/llama/merge_lora.py` | LoRA merge tool |

---

## Verification Plan

### After Phase 0 (Prerequisites)
- `ffmpeg -version` succeeds
- `fish_env/bin/python -c "from fish_speech.utils.schema import ServeTTSRequest"` prints OK
- `ls checkpoints/s2-pro/model.pth` exists
- `pip show anthropic` shows installed

### After Phase 1 (Seed Prep)
- `ffprobe dataset_pipeline/master_seed.wav` → 44100 Hz, mono, PCM s16
- `dataset_pipeline/master_seed.txt` contains accurate transcript

### After Phase 2 (Test Batch)
- 9 WAV files in `test_audio/`, each >1KB
- User confirms voice identity matches seed
- User confirms tags produce audible emotional variation

### After Phase 3 (Script Generation)
- `wc -l dataset_pipeline/master_script.jsonl` = 7500
- Category distribution: `grep -c '"A"' master_script.jsonl` = 3000, B=2250, C=2250
- Spot check: no sentences with >2 tags

### After Phase 4 (Factory Loop)
- `ls dataset_pipeline/audio/*.wav | wc -l` = 7500
- `ls dataset_pipeline/audio/*.lab | wc -l` = 7500
- Spot check random samples for audio quality
- `.lab` files contain original (pre-translation) tags

### After Phase 5 (Training)
- `ls data/quantized-dataset-ft/*.protos` exists
- Training loss converges (check tensorboard)
- `ls checkpoints/s2-pro-finetuned/model.pth` exists
- Test merged model: generate a few samples and compare to base S2 Pro
