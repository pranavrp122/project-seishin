# VAD Integration Spec — Silero VAD Gatekeeper

**Author**: Archie (Architecture Agent)
**Status**: Approved for Implementation
**Target file**: `scripts/nexus_engine.py`

---

## Problem Statement

The current implementation polls audio from a rolling 2-second buffer and uses a fixed
`SILENCE_THRESHOLD = 1.3s` timer to decide when the user has finished speaking. This approach
has two failure modes:

1. **Ghost words**: Parakeet runs on every buffer tick, including frames that contain only
   background noise or partial phonemes. The model hallucinates short tokens (`"the"`, `"a"`,
   `"um"`) which reset `last_speech_time` and prevent the silence gate from ever triggering.

2. **Fixed-latency bias**: 1.3 s is a worst-case guess. Fast utterances ("yes", "stop") always
   incur the full wait. Longer sentences may be cut early if the speaker pauses briefly mid-thought.

## Solution: Silero VAD as a Pre-ASR Gatekeeper

Silero VAD is a lightweight ONNX/Torch model (~1 MB) that outputs a speech probability score
per 512-sample chunk (32 ms at 16 kHz). Placing it before Parakeet means:

- Parakeet only runs on confirmed speech segments — eliminates ghost words
- Silence detection is driven by acoustic reality, not a wall-clock timer
- CPU-resident — zero GPU contention with Parakeet

## Architecture

```
Mic callback (800-sample chunks @ 16 kHz)
        │
        ▼
[ VAD Ring Buffer ]  ← accumulate until full chunk (512 samples)
        │
        ▼
[ Silero VAD ]  (CPU, torch.hub model in inference mode)
  speech_prob per chunk
        │
   ┌────┴────┐
   │         │
 > 0.5     ≤ 0.5
 (speech)  (silence)
   │         │
   ▼         └──── silence_counter++
[ Append to ASR buffer ]
   │              if silence_counter >= SILENCE_FRAMES:
   │                  → flush ASR buffer to Parakeet
   │                  → send to Brain
   │                  → reset all state
   ▼
[ Parakeet TDT ]  (GPU)
        │
        ▼
[ ask_brain() ]  (HTTP stream to vLLM)
```

## Parameters

| Parameter | Value | Rationale |
|---|---|---|
| `VAD_CHUNK_SAMPLES` | `512` | Silero's required chunk size at 16 kHz |
| `VAD_SAMPLE_RATE` | `16000` | Must match mic and Parakeet |
| `VAD_SPEECH_THRESHOLD` | `0.5` | Silero default; tune down to 0.35 for noisy rooms |
| `VAD_SILENCE_FRAMES` | `15` | 15 × 32 ms = ~480 ms of silence → end of utterance |
| `VAD_MIN_SPEECH_FRAMES` | `5` | Ignore bursts shorter than 5 frames (~160 ms); filters clicks |
| `VAD_MAX_BUFFER_SECONDS` | `10` | Hard cap on ASR buffer to prevent memory growth |

`VAD_SILENCE_FRAMES = 15` replaces the old `SILENCE_THRESHOLD = 1.3`. The effective silence
gate is now 480 ms, which is empirically fast for natural conversation while still robust to
brief mid-sentence pauses (which typically last < 300 ms).

## State Machine

```
IDLE
  │  speech_prob > VAD_SPEECH_THRESHOLD for >= VAD_MIN_SPEECH_FRAMES
  ▼
SPEAKING  ← append chunk to asr_buffer, reset silence_counter
  │  speech_prob <= VAD_SPEECH_THRESHOLD
  ▼
TRAILING  ← silence_counter++
  │  silence_counter >= VAD_SILENCE_FRAMES
  ▼
FLUSH  → run Parakeet on asr_buffer → ask_brain() → back to IDLE
  │  speech_prob > VAD_SPEECH_THRESHOLD (user starts again before flush)
  ▼
SPEAKING  (re-enter, keep accumulated buffer)
```

## Model Loading

```python
# Load once at startup — CPU-resident, inference mode
vad_model, vad_utils = torch.hub.load(
    repo_or_dir='snakers4/silero-vad',
    model='silero_vad',
    force_reload=False
)
(get_speech_timestamps, _, _, VADIterator, _) = vad_utils
vad_model.train(False)  # put model in inference mode (equivalent to model.eval())
```

`torch.hub` caches the model in `~/.cache/torch/hub/`. Inside the container, ensure the
cache directory is writable or pre-seeded to avoid re-downloading on each restart.

## Removed Code

The following logic is **deleted** in the new implementation:

- `SILENCE_THRESHOLD = 1.3` constant
- `last_speech_time` variable
- `last_text` deduplication guard (ghost-word workaround)
- The full Parakeet decode-on-every-tick loop

## Container Constraints

- Silero loads via `torch.hub` — requires internet access on first run, or a pre-cached model
- The NeMo 26.02 image ships with PyTorch >= 2.0, which is compatible with Silero
- No new pip installs required; `onnxruntime` is optional (Silero uses native Torch by default)

## Testing Criteria

| Test | Pass Condition |
|---|---|
| Background noise only | No ASR invocations over 30 s |
| Single word ("stop") | Exactly 1 ASR + 1 Brain call within 700 ms of word end |
| Natural sentence | Flush triggers <= 600 ms after trailing silence |
| Mid-sentence pause (< 300 ms) | No premature flush |
| Max buffer guard | Buffer capped at `VAD_MAX_BUFFER_SECONDS × RATE` samples |
