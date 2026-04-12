# Requirements: Fish Speech S2-Pro Optimization

**Defined:** 2026-04-10
**Core Value:** Identical voice quality to upstream with minimal VRAM and fastest possible RTF

## v1 Requirements

### Environment Setup

- [x] **ENV-01**: Python venv created with all Fish Speech dependencies installed
- [x] **ENV-02**: Server launches successfully on clean upstream code

### Soundfile Fix

- [x] **SFX-01**: reference_loader.py uses soundfile instead of torchaudio.load
- [x] **SFX-02**: Server generates clips without torchcodec crash

### INT8 Quantization + Compile

- [x] **OPT-01**: INT8 W8A16 quantization applied via Int8WeightOnlyConfig in inference.py
- [x] **OPT-02**: torch.compile with mode="reduce-overhead", fullgraph=False enabled in inference.py
- [x] **OPT-03**: DAC causal mask reduced from 32768x32768 to 4096x4096 in modded_dac.py
- [x] **OPT-04**: Server starts with --compile flag

### TF32 Precision

- [x] **TF32-01**: torch.set_float32_matmul_precision("high") added before quantization in init_model()

### Verification

- [x] **VER-01**: Benchmark produces 6 clips with variable lengths (3-11s)
- [x] **VER-02**: All clips have RTF < 0.3x (exceeded original 0.5x target)
- [x] **VER-03**: VRAM usage 8.88-9.2GB (exceeded original 9.74GB target)
- [x] **VER-04**: Voice quality matches reference with presence EQ for crispness

### Experimental Optimizations

- [ ] **EXP-01**: Research at least 3 cutting-edge optimization techniques with real-world evidence
- [ ] **EXP-02**: Test each technique in isolation against stable baseline (tag stable-v1.0)
- [ ] **EXP-03**: Any technique improving VRAM or RTF without quality loss is committed
- [ ] **EXP-04**: Rejected techniques documented with evidence in CHANGES.md

## v2 Requirements

None — this is a single-milestone optimization task.

## Out of Scope

| Feature | Reason |
|---------|--------|
| FP8 quantization | Rejected, 2-3x slower than BF16 (Step 2) |
| NVFP4 W4A16 | Rejected, more VRAM and slower than INT8 (Step 4) |
| NVFP4 W4A4 + MSLK | Rejected, 2x slower than INT8 (Step 5) |
| INT4 W4A16 | CUTLASS crash on SM120/RTX 5090 (Step 6) |
| SGLang-Omni | 1.4-2x RTF, worse than native for single-stream (Step 8) |
| Full pedalboard chain | Over-processed output, flattened dynamics (Step 10) |
| Multi-voice support | Not in scope for optimization task |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 | Phase 1 | Complete |
| ENV-02 | Phase 1 | Complete |
| SFX-01 | Phase 1 | Complete |
| SFX-02 | Phase 1 | Complete |
| OPT-01 | Phase 2 | Complete |
| OPT-02 | Phase 2 | Complete |
| OPT-03 | Phase 2 | Complete |
| OPT-04 | Phase 2 | Complete |
| TF32-01 | Phase 3 | Complete |
| VER-01 | Phase 3 | Complete |
| VER-02 | Phase 3 | Complete |
| VER-03 | Phase 3 | Complete |
| VER-04 | Phase 3 | Complete |
| EXP-01 | Phase 4 | Pending |
| EXP-02 | Phase 4 | Pending |
| EXP-03 | Phase 4 | Pending |
| EXP-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-12 after Phase 4 addition*
