# Requirements: Gemma 4 NVFP4 + TurboQuant KV Test

**Defined:** 2026-04-14
**Core Value:** Prove Gemma 4 26B-A4B fits under 18GB VRAM with acceptable quality and throughput on RTX 5090

## v1 Requirements

Requirements for validating Gemma 4 as a Nexus Engine LLM replacement.

### Environment Setup

- [ ] **ENV-01**: Docker environment runs vLLM built from PR #38479 with Alberto-Codes' Gemma 4 fixes on RTX 5090
- [ ] **ENV-02**: NVFP4 model (bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4) downloaded and accessible to container
- [ ] **ENV-03**: gemma4_patched.py correctly mounted and replaces stock vLLM Gemma 4 model file
- [ ] **ENV-04**: All required environment variables set (VLLM_NVFP4_GEMM_BACKEND=marlin, PYTORCH_CUDA_ALLOC_CONF, VLLM_WORKER_MULTIPROC_METHOD=spawn)

### Baseline Validation (NVFP4 + FP8 KV)

- [ ] **BASE-01**: vLLM server starts and loads NVFP4 model without errors
- [ ] **BASE-02**: Model generates coherent text responses via OpenAI-compatible API
- [ ] **BASE-03**: Actual VRAM usage measured at idle (model loaded, no active requests)
- [ ] **BASE-04**: VRAM usage measured under load at 4K, 8K, 16K, and 32K context lengths
- [ ] **BASE-05**: Model + KV cache fits under 18GB at usable context length (target: 32K+)

### TurboQuant KV Compression

- [ ] **TQ-01**: vLLM starts with --kv-cache-dtype turboquant_k8v4 alongside NVFP4 weights
- [ ] **TQ-02**: TQ KV produces coherent output (no quality collapse from KV compression)
- [ ] **TQ-03**: VRAM usage measured with TQ KV at same context lengths as baseline
- [ ] **TQ-04**: VRAM savings from TQ KV quantified vs FP8 KV baseline

### Benchmarking

- [ ] **BENCH-01**: Generation throughput measured (tokens/sec) for single-turn responses
- [ ] **BENCH-02**: Prefill speed measured (tokens/sec) for prompt processing
- [ ] **BENCH-03**: Time-to-first-token (TTFT) measured for various prompt lengths
- [ ] **BENCH-04**: Multi-turn conversation quality validated (instruction following, coherence, personality)

### Comparison

- [ ] **CMP-01**: Side-by-side VRAM comparison: NVFP4+FP8 vs NVFP4+TQ at each context length
- [ ] **CMP-02**: Side-by-side throughput comparison: NVFP4+FP8 vs NVFP4+TQ
- [ ] **CMP-03**: Go/no-go decision documented with evidence for pipeline integration

## v2 Requirements

Deferred to pipeline integration phase (separate project).

- **INT-01**: Integrate validated Gemma 4 build into Nexus Engine Docker Compose
- **INT-02**: Validate concurrent operation with Fish Speech and Parakeet containers
- **INT-03**: End-to-end voice companion latency test (ASR -> LLM -> TTS)
- **INT-04**: Compare Gemma 4 quality vs Qwen 3.5 9B in companion conversation

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multimodal (image/audio) inputs | Text-only evaluation for companion use case |
| Multi-user serving | Single-user companion pipeline |
| llama.cpp path | NVFP4 CUDA kernels not implemented (Issue #21777) |
| MXFP4-MOE format | Decided on NVFP4 for native FP4 tensor core support |
| TurboQuant pip plugin | Page size conflict with NVFP4; using native PR #38479 instead |
| Pipeline integration | Separate project after validation |
| Context > 64K testing | Companion use case needs ~8K-32K max |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 | Phase 1 | Pending |
| ENV-02 | Phase 1 | Pending |
| ENV-03 | Phase 1 | Pending |
| ENV-04 | Phase 1 | Pending |
| BASE-01 | Phase 2 | Pending |
| BASE-02 | Phase 2 | Pending |
| BASE-03 | Phase 2 | Pending |
| BASE-04 | Phase 2 | Pending |
| BASE-05 | Phase 2 | Pending |
| BENCH-01 | Phase 2 | Pending |
| BENCH-02 | Phase 2 | Pending |
| BENCH-03 | Phase 2 | Pending |
| BENCH-04 | Phase 2 | Pending |
| TQ-01 | Phase 3 | Pending |
| TQ-02 | Phase 3 | Pending |
| TQ-03 | Phase 3 | Pending |
| TQ-04 | Phase 3 | Pending |
| CMP-01 | Phase 3 | Pending |
| CMP-02 | Phase 3 | Pending |
| CMP-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0

---
*Requirements defined: 2026-04-14*
*Last updated: 2026-04-14 after roadmap creation*
