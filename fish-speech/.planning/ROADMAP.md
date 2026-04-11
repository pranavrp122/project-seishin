# Roadmap: Fish Speech S2-Pro Optimization

## Overview

Three sequential phases that take Fish Speech S2-Pro from stock (broken audio loading, high VRAM, slow inference) to optimized (stable generation, ~9.74GB VRAM, RTF < 0.5x). Each phase builds on the last and must be verified before proceeding. Phase 1 gets a working baseline, Phase 2 applies the core optimizations, Phase 3 adds TF32 and runs final verification.

## Phases

- [ ] **Phase 1: Baseline + Soundfile Fix** - Working Fish Speech environment with stable audio generation
- [ ] **Phase 2: INT8 Quantization + Compile + DAC Mask** - Core optimizations for VRAM and speed
- [ ] **Phase 3: TF32 + Final Verification** - Last optimization pass and full benchmark validation

## Phase Details

### Phase 1: Baseline + Soundfile Fix
**Goal**: Fish Speech server runs and generates audio clips without crashes
**Depends on**: Nothing (first phase)
**Requirements**: ENV-01, ENV-02, SFX-01, SFX-02
**Success Criteria** (what must be TRUE):
  1. Python venv exists at /home/prana/fish-speech/fish_env with all Fish Speech dependencies installed
  2. Fish Speech server starts and accepts TTS requests without errors
  3. reference_loader.py uses soundfile instead of torchaudio.load for audio loading
  4. Server generates audio clips from reference audio without crashing
**Plans**: TBD

### Phase 2: INT8 Quantization + Compile + DAC Mask
**Goal**: Fish Speech runs with significantly reduced VRAM and faster inference through quantization, compilation, and mask optimization
**Depends on**: Phase 1
**Requirements**: OPT-01, OPT-02, OPT-03, OPT-04
**Success Criteria** (what must be TRUE):
  1. Text2semantic model is quantized to INT8 W8A16 via Int8WeightOnlyConfig in inference.py
  2. torch.compile with reduce-overhead mode is applied to the text2semantic model
  3. DAC causal mask is 4096x4096 instead of 32768x32768 in modded_dac.py
  4. Server starts with --compile flag, VRAM usage is ~9.74GB, and RTF is improved over Phase 1 baseline
**Plans**: TBD

### Phase 3: TF32 + Final Verification
**Goal**: All optimizations are active and verified through a full benchmark proving VRAM, speed, and quality targets are met
**Depends on**: Phase 2
**Requirements**: TF32-01, VER-01, VER-02, VER-03, VER-04
**Success Criteria** (what must be TRUE):
  1. torch.set_float32_matmul_precision("high") is set before quantization in inference.py
  2. Full benchmark of 5 clips at variable lengths (3-11s) completes successfully
  3. All benchmark clips achieve RTF < 0.5x
  4. VRAM stays at or below ~9.74GB throughout the benchmark
  5. Generated voice quality has no distortion, artifacts, or degradation
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Baseline + Soundfile Fix | 0/0 | Not started | - |
| 2. INT8 Quantization + Compile + DAC Mask | 0/0 | Not started | - |
| 3. TF32 + Final Verification | 0/0 | Not started | - |
