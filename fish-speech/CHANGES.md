# Fish Speech S2 Pro — Change Log

Each step: what changed, VRAM, RTF, quality result.

---

## Key Lessons

1. **Reference audio length matters**: Short per-emotion clips (3-7s) gave bad voice cloning. `master_seed.wav` (17.3s) = perfect quality. Always use a long, representative reference.
2. **torchaudio 2.9+ breaks upstream**: `torchaudio.load()` requires torchcodec on 2.9+. Fix: use `soundfile` directly in `reference_loader.py`.
3. **Quantization alone is slower without compile**: INT8 W8A16 adds dequant overhead. FP8 W8A16 is even worse (2-3x slower). Need `torch.compile(mode="reduce-overhead")` to fuse and use CUDA graphs.
4. **Quality was never the code**: All "bad quality" reports were caused by wrong reference clips, not model code changes.
5. **Never use `--half` with INT8 quantization on a BF16-trained model**: FP16's narrow dynamic range (max 65504) causes softmax overflow through 36 layers, compounded by INT8 dequant errors. The stop token never fires and every clip generates max tokens of silence. Always use default BF16.
6. **max_seq_len is a hidden VRAM killer**: The HuggingFace checkpoint ships with `max_seq_len=32768`, which pre-allocates ~4.5GB of KV cache + 1GB causal mask. Overriding to 4096 in code (`from_pretrained(..., max_length=4096)`) saves ~4.9GB. TTS clips rarely exceed 30s (~3000 tokens), so 4096 is safe. This was previously done by editing the local `checkpoints/s2-pro/config.json` — the clean rebuild missed it because it used the unmodified HF cache path.

---

## Step 1: Baseline — Upstream + soundfile fix

**Commit**: `3dd1f85` + soundfile fix in `reference_loader.py`  
**VRAM**: ~15-16 GB | **RTF**: ~1.3x | **Quality**: CONFIRMED GOOD (master_seed.wav)

- reference_loader: soundfile instead of torchaudio.load (fixes torchcodec crash on torchaudio 2.9+)
- Everything else: pure upstream

---

## Step 2: FP8 quantization (tested, rejected)

**VRAM**: 13.26 GB | **RTF**: ~3.0x | **Quality**: untested (too slow)

FP8 weight-only dequantization overhead is not fused in TorchAO 0.18 dev — 2-3x slower than BF16 baseline. Rejected.

---

## Step 3: INT8 W8A16 + torch.compile reduce-overhead + 4k DAC mask

**Changes**:
- `inference.py`: `_quantize_model_int8()` with `Int8WeightOnlyConfig`
- `inference.py`: compile mode `reduce-overhead`, `fullgraph=False`
- `modded_dac.py`: causal mask 32768x32768 -> 4096x4096 (saves ~128MB, safe for clips up to ~47s at 86fps)
- Server started with `--compile` flag

**VRAM**: 9.74 GB | **RTF**: ~0.25x (5x faster than real-time) | **Quality**: CONFIRMED PERFECT

### Metrics
| Clip | Audio | Total | RTF |
|------|-------|-------|-----|
| 01_warm | 5.5s | 2.1s | 0.38x |
| 02_exhausted | 10.6s | 2.7s | 0.25x |
| 03_angry | 3.4s | 1.3s | 0.38x |
| 04_tender | 6.7s | 1.9s | 0.28x |
| 05_professional | 10.0s | 2.6s | 0.26x |

HuggingFace: `model_comparison/s2pro/`

### Server start command
```bash
python3 tools/api_server.py \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --decoder-config-name modded_dac_vq \
  --device cuda \
  --compile \
  --listen 127.0.0.1:8080
```

---

## Step 4: NVFP4 W4A16 (tested, rejected)

**VRAM**: 11.02 GB | **RTF**: ~1.0x | **Quality**: OK

NVFP4 weight-only via `NVFP4WeightOnlyConfig`. Scale factor overhead + unfused dequant = more VRAM and slower than INT8. Rejected.

HuggingFace: `model_comparison/s2pro_nvfp4/`

---

## Step 5: NVFP4 W4A4 + MSLK (tested, rejected)

**Stack upgrade**: PyTorch 2.12.0+cu132, torchaudio 2.11.0+cu132, mslk 2026.4.9+cu132

**VRAM**: 11.02 GB | **RTF**: ~0.5x | **Quality**: OK

| Clip | Audio | Total | RTF |
|------|-------|-------|-----|
| 01_warm | 5.1s | 3.5s | 0.69x |
| 02_exhausted | 10.7s | 5.0s | 0.47x |
| 03_angry | 3.9s | 2.2s | 0.56x |
| 04_tender | 6.7s | 3.2s | 0.48x |
| 05_professional | 9.5s | 4.3s | 0.45x |

2x faster than W4A16 but still 2x slower than INT8. More VRAM than INT8. Rejected.

HuggingFace: `model_comparison/s2pro_nvfp4_w4a4/`

---

## Step 6: INT4 W4A16 (tested, crashed)

CUTLASS crash on SM120 (RTX 5090) with cu132 nightly. `Int4WeightOnlyConfig` at every group size returns `cutlass cannot initialize`. Dead end on this CUDA stack.

---

## Step 7: INT8 + TF32 ✅ CURRENT BEST

**Changes**:
- Added `torch.set_float32_matmul_precision("high")` before quantization in `init_model()`
- Everything else same as Step 3

**VRAM**: 9.74 GB | **RTF**: ~0.20x (5x faster than real-time) | **Quality**: CONFIRMED PERFECT

### Metrics
| Clip | Audio | Total | RTF |
|------|-------|-------|-----|
| 01_warm | 5.4s | 1.8s | 0.33x |
| 02_exhausted | 10.4s | 2.5s | 0.24x |
| 03_angry | 3.3s | 1.1s | 0.33x |
| 04_tender | 6.4s | 1.8s | 0.28x |
| 05_professional | 9.9s | 2.4s | 0.24x |

~10-15% faster than Step 3 with zero quality or VRAM cost. TF32 enables lower-precision float32 intermediates (layer norms, softmax) -- free speed.

HuggingFace: `model_comparison/s2pro_int8_tf32/`

### Server start command
```bash
./start_server.sh \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --decoder-config-name modded_dac_vq \
  --device cuda \
  --compile \
  --listen 127.0.0.1:8080
```

Note: `start_server.sh` sets `LD_LIBRARY_PATH` for cu13 libs (needed for MSLK/NVFP4).

---

## Step 8: SGLang-Omni INT8+TF32 (tested, slower -- RTX 5090 SM120 limitations)

**Repo**: `/home/prana/sglang-omni` (separate venv, torch 2.9.1)

**VRAM**: 32 GB (85% pre-allocated for KV cache, 27 GB reserved regardless of request size)  
**RTF**: ~1.4-2.0x (after reference audio cache) | **Quality**: same (same model weights)

### Workarounds needed for SM120 (RTX 5090 Blackwell)
- `sgl_kernel` ships Hopper-only (SM90) flash attention -> replaced with SDPA fallback in `modeling.py`
- `flashinfer` JIT needs `nvcc` -> installed via micromamba at `/home/prana/cuda-toolkit`
- CUDA graphs work with `attention_backend="triton"` (radix attention path) + SDPA fallback (audio decoder fast head)

### Why slower than native
1. **Triton attention** instead of compiled flash attention -- no SM120 kernel in sgl_kernel 0.3.21
2. **Audio decoder not graph-captured** -- `_decode_codebooks` (9 codebooks x N tokens) runs in eager mode
3. **KV pre-allocation** -- 85% of 32GB reserved upfront vs native's dynamic allocation
4. **Reference encoding overhead** -- 18s cold, ~0s warm (added path cache to `stages.py`)

### Metrics (after 1 warmup request to cache ref audio)
| Clip | Audio | Total | RTF |
|------|-------|-------|-----|
| 01_warm | 5.8s | 8.1s | 1.40x |
| 02_exhausted | 10.7s | 20.8s | 1.94x |
| 03_angry | 3.6s | 7.3s | 2.05x |
| 04_tender | 7.1s | 12.9s | 1.82x |
| 05_professional | 9.9s | 19.8s | 2.00x |

HuggingFace: `model_comparison/s2pro_sglang_int8_tf32_cached/`

### Key lesson
SGLang-Omni's advantage (prefix caching / RadixAttention) only pays off at scale (many concurrent requests reusing the same reference tokens). For single-voice single-stream use, the Fish Speech native INT8+TF32+compile setup is significantly better. SGLang-Omni will become competitive once `sgl_kernel` ships SM120 kernels (tracked: sgl-project/sglang#7227).

---

## Step 9: Clean Rebuild -- INT8 + TF32 + max_seq_len override + inductor fusion ✅ STABLE

**Date**: 2026-04-11
**Repo**: `/home/prana/fish-speech` (fresh clone of upstream)
**Stack**: torch 2.8.0+cu128, torchaudio 2.8.0+cu128, torchao 0.12.0+cu128, CUDA 13.0 toolkit

**Changes** (all in code, no config file edits):
- `inference.py`: `from_pretrained(..., max_length=4096)` -- overrides HF checkpoint's `max_seq_len=32768` to reduce KV cache from ~4.5GB to ~0.56GB
- `inference.py`: `torch.set_float32_matmul_precision("high")` -- TF32 for free 10-15% speed boost
- `inference.py`: `quantize_(model, Int8WeightOnlyConfig())` -- INT8 W8A16 weight-only quantization
- `inference.py`: `torch.compile(mode="reduce-overhead", fullgraph=False)` -- CUDA graph fusion
- `inference.py`: `force_fuse_int_mm_with_mul = True` + inductor coordinate descent tuning -- fuses INT8 dequant with matmul for ~5% throughput boost
- `modded_dac.py`: causal mask 32768x32768 -> 4096x4096 (saves ~128MB)
- `reference_loader.py`: soundfile instead of torchaudio.load (fixes torchcodec crash)
- `__init__.py`: removed per-request `torch.cuda.empty_cache()` + `gc.collect()` -- was adding ~1s overhead per request by forcing CUDA memory pool teardown/rebuild
- `schema.py`: default temperature 0.8->0.85, repetition_penalty 1.2->1.1 (tuned for more natural speech with contractions)
- Server flags: `--compile` (NO `--half` -- see warning below)
- Env var: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`

**VRAM**: 8.88 GB | **RTF**: ~0.27x (4x faster than real-time) | **Quality**: CONFIRMED GOOD

### Generation defaults
| Parameter | Value |
|-----------|-------|
| temperature | 0.85 |
| top_p | 0.8 |
| repetition_penalty | 1.1 |
| max_new_tokens | 1024 |
| chunk_length | 200 |

### Metrics (after 3 warmup requests)
| Clip | Audio | Total | RTF |
|------|-------|-------|-----|
| 01_warm | 5.6s | 1.9s | 0.34x |
| 02_exhausted | 9.8s | 2.6s | 0.27x |
| 03_angry | 3.7s | 1.1s | 0.31x |
| 04_tender | 6.6s | 1.9s | 0.29x |
| 05_professional | 9.7s | 2.6s | 0.27x |
| 06_playful | 6.7s | 1.8s | 0.27x |

HuggingFace: `model_comparison/s2pro_int8_tf32_stable/`

### Key differences from Steps 3/7
1. **max_seq_len override in code**: Steps 3/7 achieved 9.74GB by silently editing the local `checkpoints/s2-pro/config.json` to set `max_seq_len: 4096`. The clean rebuild applies the override explicitly via `from_pretrained(..., max_length=4096)`, making it reproducible.
2. **`expandable_segments` allocator**: Reduces CUDA memory fragmentation. Combined with the code-level max_seq_len override, VRAM is 8.88GB vs 9.74GB.
3. **Inductor fusion**: `force_fuse_int_mm_with_mul` fuses INT8 dequantization with matmul, eliminating the intermediate int32 tensor allocation. ~5% throughput improvement.
4. **No per-request cache clearing**: Removed `torch.cuda.empty_cache()` + `gc.collect()` that ran after every TTS request. This was forcing CUDA to teardown and rebuild memory pools, adding ~1s per request. On a dedicated TTS server with stable VRAM this is pure overhead.
5. **Warmup**: 3 warmup requests with varying text lengths before benchmarking. This ensures CUDA graphs are fully compiled and memory pools are stable.
6. **No `--half` flag**: See warning below.

### WARNING: Do NOT use `--half` with INT8 quantization
The `--half` flag forces FP16 precision. This model was trained in BF16. FP16's narrow dynamic range (max 65504 vs BF16's 3.4e38) causes softmax overflow through 36 transformer layers, especially compounded with INT8 dequantization errors. Result: the im_end stop token never gets enough probability to be sampled, and every clip generates exactly `max_new_tokens` (1024 tokens = 47.5s of silence). Always use the default BF16 precision.

### WARNING: Do NOT upgrade to PyTorch 2.10+ or CUDA 13.x
Confirmed 40-55% throughput regression in `reduce-overhead` mode on PyTorch 2.10 vs 2.9 (pytorch/pytorch#174575). CUDA 13.x toolkit is a secondary contributor to the regression. Stay on torch 2.8.0+cu128 until the regression is resolved.

### Server start command
```bash
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export ENABLE_SM120=1
export CUDA_HOME="/home/prana/cuda13-toolkit/targets/x86_64-linux"
export PATH="/home/prana/cuda13-toolkit/bin:$PATH"
export LD_LIBRARY_PATH="/home/prana/cuda13-toolkit/targets/x86_64-linux/lib:/usr/local/lib/ollama/mlx_cuda_v13:${LD_LIBRARY_PATH:-}"

python3 tools/api_server.py \
  --llama-checkpoint-path $HF_CHECKPOINT \
  --decoder-checkpoint-path $HF_CHECKPOINT/codec.pth \
  --decoder-config-name modded_dac_vq \
  --device cuda \
  --compile \
  --listen 127.0.0.1:8080
```

### Warm-up (run after server starts, before serving traffic)
Send 3 requests with short/medium/long text to compile CUDA graphs for different sequence lengths. First request triggers ~140s compilation; subsequent requests are fast.

---

## Step 10: Generation parameter tuning + presence EQ ✅ CURRENT

**Date**: 2026-04-12
**Status**: Tuned generation params + minimal presence EQ committed

### Generation parameter changes (from Step 9 defaults)
| Parameter | Step 9 | Step 10 | Why |
|-----------|--------|---------|-----|
| temperature | 0.85 | 0.875 | Higher emotion ceiling — more expressive range for tagged emotions |
| repetition_penalty | 1.1 | 1.05 | Less repetition suppression = more natural prosody variation |
| chunk_length | 200 | 350 | Fewer chunk seams — eliminates choppy phrasing on longer sentences |

### Post-processing: presence-only EQ (committed) ✅
```python
Pedalboard([
    PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7),
])
```
A single parametric EQ band centered at 3.5kHz adds consonant clarity/crispness without altering dynamics, loudness, or voice character. No compressor, no limiter, no noise gate — the raw generation is already clean enough.

Full 5-stage chain (highpass + noise gate + compressor + shelf + limiter) was A/B tested and rejected — it over-processed the output, flattening dynamics and adding unnatural loudness consistency.

### Metrics (presence EQ, tuned gen params)
| Clip | Audio | Total | RTF | VRAM | Peak dB | RMS dB |
|------|-------|-------|-----|------|---------|--------|
| 01_warm | 5.4s | 1.5s | 0.272x | 9403 MB | -0.3 | -15.2 |
| 02_exhausted | 10.5s | 2.6s | 0.245x | 9863 MB | -2.1 | -15.5 |
| 03_angry | 3.5s | 1.0s | 0.294x | 9221 MB | -0.3 | -15.5 |
| 04_tender | 7.3s | 1.9s | 0.256x | 9563 MB | -2.6 | -15.9 |
| 05_professional | 9.7s | 2.4s | 0.249x | 9803 MB | -1.6 | -16.7 |
| 06_playful | 7.0s | 1.8s | 0.260x | 9543 MB | -0.0 | -16.7 |

**RTF**: 0.263x mean | **VRAM**: ~9.2-9.9 GB (same as Step 9 — single EQ band adds zero measurable overhead)

### HuggingFace test clips
All voice filter test clips are organized under `voice_filter_test/`:
- `01_baseline_no_filter/` — Step 9 defaults (temp=0.85, rep=1.1, chunk=200), no filter
- `02_tuned_params_no_filter/` — tuned gen params (temp=0.875, rep=1.05, chunk=350), no filter
- `03_tuned_filter/` — tuned gen params + full 5-stage pedalboard chain (rejected)
- `04_presence_eq/` — tuned gen params + presence-only EQ (committed)

Previous A/B filter tests remain at:
- `model_comparison/s2pro_filter_harsh/` — aggressive 5-stage chain
- `model_comparison/s2pro_filter_tuned/` — research-tuned 5-stage chain

---

## Step 11: Streaming pipeline + sub-chunk audio ✅ STABLE (v1.8-streaming-stable)

**Date**: 2026-04-12 — 2026-04-13
**Tag**: `v1.8-streaming-stable`
**Status**: Streaming pipeline complete, sub-chunk decode working. Robustness phase (Phase 4) deferred to later.

### Changes

**Phase 1 — Text Splitting & Emotion Propagation:**
- `inference.py`: `split_text_into_chunks()` — regex-based clause/sentence boundary splitting
- First chunk targets 30-80 bytes (fast TTFA), subsequent chunks 100-200 bytes
- Emotion tags (`[angry]`, `[warm]`, etc.) extracted and propagated to every chunk
- Mid-text emotion transitions tracked per chunk

**Phase 2 — Streaming Pipeline & Audio Quality:**
- `inference_engine/crossfader.py`: `StreamingCrossfader` — equal-power sin²/cos² crossfade at chunk boundaries (1764 samples overlap at 44.1kHz)
- `inference_engine/utils.py`: `wav_chunk_header()` — WAV header with 0xFFFFFFFF sizes for streaming
- `inference_engine/__init__.py`: wired crossfader into inference loop, per-chunk PeakFilter post-FX
- Consistent int16 PCM encoding throughout streaming path

**Phase 3 — Sub-Chunk Audio Streaming:**
- `models/text2semantic/inference.py`: `generate_long()` / `generate()` / `decode_n_tokens()` converted to yield partial VQ code tensors every N tokens (`sub_chunk_tokens` parameter)
- `inference_engine/__init__.py`: grow-and-redecode consumer — DAC decoder re-decodes full accumulated VQ tokens each partial, emits only new samples
- Text-chunk boundary crossfade via manual prev_batch_tail buffer (bypasses StreamingCrossfader for sub-chunk mode)
- `utils/schema.py`: `sub_chunk_tokens` parameter added to `ServeTTSRequest`

### Performance (streaming, sub_chunk_tokens=10, chunk_length=200)
| Clip | Audio | TTFA | Total | RTF |
|------|-------|------|-------|-----|
| 01_warm | 5.5s | ~250ms | 2.1s | 0.38x |
| 02_exhausted | 10.6s | ~250ms | 3.0s | 0.28x |
| 03_angry | 3.4s | ~250ms | 1.4s | 0.41x |
| 04_tender | 6.7s | ~250ms | 2.0s | 0.30x |
| 05_professional | 10.0s | ~250ms | 2.8s | 0.28x |

**TTFA**: ~250ms (down from ~1.5s baseline)
**RTF**: ~0.33x mean (slightly higher than non-streaming due to sub-chunk re-decode overhead)
**VRAM**: ~9.2-9.9 GB (same as Step 10 — streaming adds negligible overhead)

### Architecture
```
Text → split_text_into_chunks() → [chunk₁, chunk₂, ...]
  ↓
Per chunk: DualAR generate → yield partial VQ codes every N tokens
  ↓
grow-and-redecode: DAC(all_codes_so_far) → emit new_samples only
  ↓
Text-chunk boundary: prev_batch_tail crossfade (sin²/cos² 1764 samples)
  ↓
WAV header (0xFFFFFFFF) + int16 PCM segments → HTTP chunked response
```

### Known limitations
- CUDA graph recompilation from variable prompt lengths may cause 100-500ms latency spikes (deferred)
- Context overflow at ~3000-3500 tokens for long texts (deferred)
- Non-streaming backward compatibility not yet validated (Phase 4 deferred)
- Sub-chunk RTF slightly higher than batch mode due to repeated DAC decode

---

## Step 12: BF16 native precision (FISH_QUANT gate) + max_seq_len 4096→8192

**Date**: 2026-04-17
**Status**: Implemented, pending A/B test

### Changes (`inference.py`)
- `from_pretrained(..., max_length=8192)` — raised from 4096; better prosodic coherence on longer multi-clause responses
- `FISH_QUANT` env var gate: default `none` = native BF16 (no quantization). Set `FISH_QUANT=int8` to restore previous INT8 W8A16 behavior.
- INT8-specific inductor config (`force_fuse_int_mm_with_mul`, coordinate descent) gated behind `_quant == "int8"` — not applied in BF16 mode.

### Why BF16 now
Gemma 4 moved to AWS EC2, freeing ~12 GB VRAM on the 5090. Parakeet ASR (3 GB) replaces the old cloud whisper call. Combined Fish Speech + Parakeet footprint is ~13 GB, leaving ~7 GB headroom — enough to run S2-Pro at full BF16 precision.

BF16 is the model's native training dtype. INT8 W8A16 was a VRAM optimization we no longer need. Community benchmarks (ComfyUI) show BF16 is often faster than bitsandbytes INT8 per token because dequant overhead disappears.

### Expected VRAM
~14-16 GB (vs ~9.9 GB INT8) — well within the ~20 GB budget.

### To revert to INT8
```bash
export FISH_QUANT=int8
./start_server.sh --compile ...
```
