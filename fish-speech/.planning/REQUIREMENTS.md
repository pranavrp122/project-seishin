# Requirements: Fish Speech S2-Pro Optimization

**Defined:** 2026-04-10
**Core Value:** Identical voice quality to upstream with <10GB VRAM and RTF < 0.5x

## v1 Requirements

### Environment Setup

- [ ] **ENV-01**: Python venv created with all Fish Speech dependencies installed
- [ ] **ENV-02**: Server launches successfully on clean upstream code

### Soundfile Fix

- [ ] **SFX-01**: reference_loader.py uses soundfile instead of torchaudio.load
- [ ] **SFX-02**: Server generates clips without torchcodec crash

### INT8 Quantization + Compile

- [ ] **OPT-01**: INT8 W8A16 quantization applied via Int8WeightOnlyConfig in inference.py
- [ ] **OPT-02**: torch.compile with mode="reduce-overhead", fullgraph=False enabled in inference.py
- [ ] **OPT-03**: DAC causal mask reduced from 32768x32768 to 4096x4096 in modded_dac.py
- [ ] **OPT-04**: Server starts with --compile flag

### TF32 Precision

- [ ] **TF32-01**: torch.set_float32_matmul_precision("high") added before quantization in init_model()

### Verification

- [ ] **VER-01**: Benchmark produces 5 clips with variable lengths (3-11s)
- [ ] **VER-02**: All clips have RTF < 0.5x
- [ ] **VER-03**: VRAM usage ~9.74GB
- [ ] **VER-04**: Voice quality matches reference (subjective check)

## v2 Requirements

None — this is a single-milestone optimization task.

## Out of Scope

| Feature | Reason |
|---------|--------|
| FP8 quantization | 2-3x slower than BF16, dequant not fused in TorchAO |
| NVFP4 W4A16 | More VRAM (11GB) and slower than INT8 |
| NVFP4 W4A4 + MSLK | 2x slower than INT8 despite being faster than W4A16 |
| INT4 W4A16 | CUTLASS crash on SM120/RTX 5090 |
| SGLang-Omni integration | 1.4-2x RTF, worse for single-stream use |
| Multi-voice support | Not in scope for this optimization task |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 | Phase 1 | Pending |
| ENV-02 | Phase 1 | Pending |
| SFX-01 | Phase 1 | Pending |
| SFX-02 | Phase 1 | Pending |
| OPT-01 | Phase 2 | Pending |
| OPT-02 | Phase 2 | Pending |
| OPT-03 | Phase 2 | Pending |
| OPT-04 | Phase 2 | Pending |
| TF32-01 | Phase 3 | Pending |
| VER-01 | Phase 3 | Pending |
| VER-02 | Phase 3 | Pending |
| VER-03 | Phase 3 | Pending |
| VER-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-10 after initial definition*
