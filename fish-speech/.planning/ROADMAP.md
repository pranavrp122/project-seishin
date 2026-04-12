# Roadmap: Fish Speech S2-Pro Optimization

## Overview

Four phases taking Fish Speech S2-Pro from stock to fully optimized. Phases 1-3 established the stable build (INT8+TF32+compile, 9.2GB VRAM, 0.263x RTF, presence EQ). Phase 4 is experimental research into further VRAM reduction and speed improvements on RTX 5090 (SM120 Blackwell).

## Phases

- [x] **Phase 1: Baseline + Soundfile Fix** - Working Fish Speech environment with stable audio generation
- [x] **Phase 2: INT8 Quantization + Compile + DAC Mask** - Core optimizations for VRAM and speed
- [x] **Phase 3: TF32 + Final Verification** - Last optimization pass and full benchmark validation
- [ ] **Phase 4: Experimental Optimizations** - Research and test cutting-edge techniques to push VRAM lower and RTF faster

## Phase Details

### Phase 1: Baseline + Soundfile Fix ✓
**Goal**: Fish Speech server runs and generates audio clips without crashes
**Depends on**: Nothing (first phase)
**Requirements**: ENV-01, ENV-02, SFX-01, SFX-02
**Status**: COMPLETE
**Success Criteria** (all met):
  1. ✓ Python venv exists with all Fish Speech dependencies installed
  2. ✓ Fish Speech server starts and accepts TTS requests without errors
  3. ✓ reference_loader.py uses soundfile instead of torchaudio.load
  4. ✓ Server generates audio clips from reference audio without crashing

### Phase 2: INT8 Quantization + Compile + DAC Mask ✓
**Goal**: Fish Speech runs with significantly reduced VRAM and faster inference
**Depends on**: Phase 1
**Requirements**: OPT-01, OPT-02, OPT-03, OPT-04
**Status**: COMPLETE
**Success Criteria** (all met):
  1. ✓ INT8 W8A16 quantization applied via Int8WeightOnlyConfig
  2. ✓ torch.compile with reduce-overhead mode applied
  3. ✓ DAC causal mask reduced to 4096x4096
  4. ✓ VRAM ~9.74GB, RTF ~0.25x

### Phase 3: TF32 + Final Verification ✓
**Goal**: All optimizations active and verified through full benchmark
**Depends on**: Phase 2
**Requirements**: TF32-01, VER-01, VER-02, VER-03, VER-04
**Status**: COMPLETE
**Success Criteria** (all met):
  1. ✓ TF32 matmul precision enabled
  2. ✓ Benchmark of 6 clips completed successfully
  3. ✓ All clips RTF < 0.3x (exceeded target)
  4. ✓ VRAM 8.88-9.2GB (exceeded target)
  5. ✓ Voice quality confirmed, presence EQ added for crispness

### Phase 4: Experimental Optimizations
**Goal**: Research and test cutting-edge techniques to further reduce VRAM and increase inference speed while maintaining voice quality
**Depends on**: Phase 3
**Requirements**: EXP-01, EXP-02, EXP-03, EXP-04
**Stable baseline**: Tag `stable-v1.0` / branch `stable-backup` at commit `487e2f9`
**Current metrics to beat**: VRAM 9.2GB, RTF 0.263x, quality = presence EQ + tuned gen params
**Success Criteria** (what must be TRUE):
  1. At least 3 optimization techniques researched with real-world evidence from forums/papers/benchmarks
  2. Each technique tested in isolation against the stable baseline
  3. Any technique that improves VRAM or RTF without quality regression is committed
  4. Techniques that degrade quality or regress metrics are documented and rejected
  5. Final build matches or exceeds stable baseline on all 3 axes (VRAM, RTF, quality)
**UI hint**: no
**Plans**: TBD (research-first phase)

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Baseline + Soundfile Fix | - | ✓ Complete | 2026-04-10 |
| 2. INT8 Quantization + Compile + DAC Mask | - | ✓ Complete | 2026-04-11 |
| 3. TF32 + Final Verification | - | ✓ Complete | 2026-04-12 |
| 4. Experimental Optimizations | 0/0 | ◆ Active | - |
