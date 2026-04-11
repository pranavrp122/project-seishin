# Fish Speech S2 Pro — Change Log

Each step: what changed, VRAM, RTF, quality result.

---

## Key Lessons

1. **Reference audio length matters**: Short per-emotion clips (3-7s) gave bad voice cloning. `master_seed.wav` (17.3s) = perfect quality. Always use a long, representative reference.
2. **torchaudio 2.9+ breaks upstream**: `torchaudio.load()` requires torchcodec on 2.9+. Fix: use `soundfile` directly in `reference_loader.py`.
3. **Quantization alone is slower without compile**: INT8 W8A16 adds dequant overhead. FP8 W8A16 is even worse (2-3x slower). Need `torch.compile(mode="reduce-overhead")` to fuse and use CUDA graphs.
4. **Quality was never the code**: All "bad quality" reports were caused by wrong reference clips, not model code changes.

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
- `modded_dac.py`: causal mask 32768×32768 → 4096×4096 (saves ~128MB, safe for clips up to ~47s at 86fps)
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

~10-15% faster than Step 3 with zero quality or VRAM cost. TF32 enables lower-precision float32 intermediates (layer norms, softmax) — free speed.

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

## Step 8: SGLang-Omni INT8+TF32 (tested, slower — RTX 5090 SM120 limitations)

**Repo**: `/home/prana/sglang-omni` (separate venv, torch 2.9.1)

**VRAM**: 32 GB (85% pre-allocated for KV cache, 27 GB reserved regardless of request size)  
**RTF**: ~1.4–2.0x (after reference audio cache) | **Quality**: same (same model weights)

### Workarounds needed for SM120 (RTX 5090 Blackwell)
- `sgl_kernel` ships Hopper-only (SM90) flash attention → replaced with SDPA fallback in `modeling.py`
- `flashinfer` JIT needs `nvcc` → installed via micromamba at `/home/prana/cuda-toolkit`
- CUDA graphs work with `attention_backend="triton"` (radix attention path) + SDPA fallback (audio decoder fast head)

### Why slower than native
1. **Triton attention** instead of compiled flash attention — no SM120 kernel in sgl_kernel 0.3.21
2. **Audio decoder not graph-captured** — `_decode_codebooks` (9 codebooks × N tokens) runs in eager mode
3. **KV pre-allocation** — 85% of 32GB reserved upfront vs native's dynamic allocation
4. **Reference encoding overhead** — 18s cold, ~0s warm (added path cache to `stages.py`)

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
