# Fish Speech S2-Pro Optimization

## What This Is

Fresh rebuild of Fish Speech S2-Pro inference server with INT8 quantization, torch.compile, and TF32 precision optimizations. Targets ~9.74GB VRAM and ~0.20x RTF (5x faster than real-time) on RTX 5090.

## Core Value

The optimized server must produce identical voice quality to upstream while using <10GB VRAM and achieving RTF under 0.5x.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Baseline server runs with soundfile fix (no torchaudio.load crash on 2.9+)
- [ ] INT8 W8A16 quantization applied to LLM and DAC models
- [ ] torch.compile with reduce-overhead mode enabled
- [ ] DAC causal mask reduced from 32768x32768 to 4096x4096
- [ ] TF32 matmul precision set before quantization
- [ ] Benchmark shows variable clip lengths (3-11s) and RTF < 0.5x
- [ ] VRAM usage ~9.74GB

### Out of Scope

- FP8 quantization — rejected, 2-3x slower than BF16 (Step 2)
- NVFP4 W4A16 — rejected, more VRAM and slower than INT8 (Step 4)
- NVFP4 W4A4 + MSLK — rejected, 2x slower than INT8 (Step 5)
- INT4 W4A16 — CUTLASS crash on SM120/RTX 5090 (Step 6)
- SGLang-Omni — 1.4-2x RTF, worse than native for single-stream (Step 8)

## Context

- **Repo**: `/home/prana/fish-speech` (clean upstream)
- **Model weights**: Already in HuggingFace cache at `/home/prana/.cache/huggingface/hub/models--fishaudio--s2-pro/snapshots/1de9996b6be38b745688de084d87a5633f714e4e`
- **Benchmark script**: `/home/prana/tts-test/run_s2pro.py` — generates 5 emotion clips via API
- **Server launcher**: `/home/prana/tts-test/start_direct.sh` — sets CUDA 13 env vars, launches api_server.py
- **Reference audio**: `/home/prana/project-seishin/dataset_pipeline/master_seed.wav` (17.3s, critical for quality)
- **GPU**: RTX 5090 (SM120 / Blackwell)
- **Change log**: `/home/prana/tts-test/changes/CHANGES.md` — documents every step and exact results
- **Key lesson**: Short per-emotion clips give bad cloning. master_seed.wav (17.3s) = perfect quality.
- **Key lesson**: torchaudio 2.9+ requires torchcodec; fix by using soundfile directly.

## Constraints

- **GPU memory**: Must not start any local LLM servers — GPU dedicated to this task
- **Approach**: One step at a time. Test and verify each step before moving on.
- **Fidelity**: Follow CHANGES.md log but can improvise fixes as needed for the current environment

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| INT8 W8A16 over FP8/NVFP4/INT4 | Best VRAM (9.74GB) and speed (0.20x RTF) of all tested | Validated |
| soundfile over torchaudio.load | torchaudio 2.9+ requires torchcodec, soundfile works directly | Validated |
| torch.compile reduce-overhead | Fuses INT8 dequant ops, enables CUDA graphs | Validated |
| TF32 matmul precision | ~10-15% speed boost, zero quality/VRAM cost | Validated |
| DAC mask 4096x4096 | Saves ~128MB, safe for clips up to ~47s at 86fps | Validated |

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
*Last updated: 2026-04-10 after initialization*
