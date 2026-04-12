# Fish Speech S2-Pro Optimization

## What This Is

Fish Speech S2-Pro inference server optimized with INT8 quantization, torch.compile, TF32 precision, and presence EQ. Currently at 9.2GB VRAM and 0.263x RTF on RTX 5090. Phase 4 explores experimental techniques to push these numbers further.

## Core Value

The optimized server must produce identical voice quality to upstream while using minimal VRAM and achieving the fastest possible RTF.

## Requirements

### Validated

- ✓ Baseline server runs with soundfile fix — Phase 1
- ✓ INT8 W8A16 quantization + torch.compile reduce-overhead — Phase 2
- ✓ DAC causal mask 4096x4096 — Phase 2
- ✓ TF32 matmul precision — Phase 3
- ✓ 6-clip benchmark: RTF 0.263x, VRAM 9.2GB — Phase 3
- ✓ Presence EQ (3.5kHz +1.5dB) for consonant clarity — Phase 3
- ✓ Tuned gen params (temp=0.875, rep=1.05, chunk=350) — Phase 3

### Active

- [ ] Research cutting-edge optimization techniques (forums, papers, latest PyTorch/CUDA features)
- [ ] Test each technique against stable baseline in isolation
- [ ] Commit improvements, document rejections
- [ ] Final build matches or exceeds stable on VRAM, RTF, quality

### Out of Scope

- FP8 quantization — rejected, 2-3x slower than BF16 (Step 2)
- NVFP4 W4A16 — rejected, more VRAM and slower than INT8 (Step 4)
- NVFP4 W4A4 + MSLK — rejected, 2x slower than INT8 (Step 5)
- INT4 W4A16 — CUTLASS crash on SM120/RTX 5090 (Step 6)
- SGLang-Omni — 1.4-2x RTF, worse than native for single-stream (Step 8)
- Full pedalboard chain — over-processed, flattened dynamics (Step 10)

## Context

- **Repo**: `/home/prana/project-seishin/fish-speech` (pushes to pranavrp122/project-seishin)
- **Stable backup**: Tag `stable-v1.0` / branch `stable-backup` at commit `487e2f9`
- **Model weights**: HuggingFace cache at `/home/prana/.cache/huggingface/hub/models--fishaudio--s2-pro/`
- **Server venv**: `/home/prana/fish-speech/.venv/bin/python3` (standalone repo's venv, shared)
- **Reference audio**: `/home/prana/project-seishin/dataset_pipeline/master_seed.wav` (17.3s)
- **GPU**: RTX 5090 32GB (SM120 / Blackwell)
- **Stack**: torch 2.8.0+cu128, torchaudio 2.8.0+cu128, torchao 0.12.0+cu128, CUDA 13.0 toolkit
- **Change log**: `/home/prana/project-seishin/fish-speech/CHANGES.md`
- **HuggingFace clips**: `EternalFlame549/archie-voice-test-clips`
- **Key constraint**: Do NOT upgrade to PyTorch 2.10+ (40-55% throughput regression in reduce-overhead mode)

## Constraints

- **GPU memory**: Must not start any local LLM servers — GPU dedicated to TTS
- **Quality**: No technique that degrades voice quality is acceptable, regardless of speed/VRAM gain
- **Stability**: Stable baseline must be recoverable at all times via `git checkout stable-backup`
- **PyTorch version**: Stay on 2.8.0+cu128 until reduce-overhead regression is fixed

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| INT8 W8A16 over FP8/NVFP4/INT4 | Best VRAM (9.2GB) and speed (0.263x RTF) of all tested | ✓ Good |
| soundfile over torchaudio.load | torchaudio 2.9+ requires torchcodec, soundfile works directly | ✓ Good |
| torch.compile reduce-overhead | Fuses INT8 dequant ops, enables CUDA graphs | ✓ Good |
| TF32 matmul precision | ~10-15% speed boost, zero quality/VRAM cost | ✓ Good |
| DAC mask 4096x4096 | Saves ~128MB, safe for clips up to ~47s at 86fps | ✓ Good |
| Presence EQ over full chain | Crispness without dynamics alteration | ✓ Good |
| Gen params temp=0.875/rep=1.05/chunk=350 | Better emotion range and smoother prosody | ✓ Good |
| Stay on PyTorch 2.8.0 | 2.10+ has 40-55% regression in reduce-overhead | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-12 after Phase 4 addition*
