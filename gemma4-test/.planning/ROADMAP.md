# Roadmap: Gemma 4 NVFP4 + TurboQuant KV Test

## Overview

Staged validation of Gemma 4 26B-A4B with NVFP4 weights and TurboQuant KV cache on RTX 5090 under 18GB VRAM. Phase 1 builds the Docker/vLLM environment from PR #38479. Phase 2 validates the NVFP4 baseline with FP8 KV -- measuring VRAM, throughput, and quality. Phase 3 enables TurboQuant KV compression, compares against baseline, and produces a go/no-go decision for Nexus Engine integration.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Environment Setup** - Docker + vLLM from PR #38479 with Gemma 4 patches, model downloaded
- [ ] **Phase 2: NVFP4 Baseline Validation** - Model loads, generates coherent text, VRAM and throughput measured with FP8 KV
- [ ] **Phase 3: TurboQuant + Verdict** - TQ KV enabled, compared against baseline, go/no-go decision documented

## Phase Details

### Phase 1: Environment Setup
**Goal**: Working Docker environment that can launch vLLM with NVFP4 support on RTX 5090
**Depends on**: Nothing (first phase)
**Requirements**: ENV-01, ENV-02, ENV-03, ENV-04
**Success Criteria** (what must be TRUE):
  1. Docker container starts with vLLM built from PR #38479 including Alberto-Codes' Gemma 4 fixes
  2. NVFP4 model files are downloaded and mounted into the container
  3. gemma4_patched.py is mounted and overrides the stock vLLM Gemma 4 model file
  4. All required environment variables (VLLM_NVFP4_GEMM_BACKEND, PYTORCH_CUDA_ALLOC_CONF, VLLM_WORKER_MULTIPROC_METHOD) are set in the container
**Plans**: TBD

Plans:
- [ ] 01-01: TBD

### Phase 2: NVFP4 Baseline Validation
**Goal**: Confirmed that NVFP4 + FP8 KV fits under 18GB with measured throughput and acceptable quality
**Depends on**: Phase 1
**Requirements**: BASE-01, BASE-02, BASE-03, BASE-04, BASE-05, BENCH-01, BENCH-02, BENCH-03, BENCH-04
**Success Criteria** (what must be TRUE):
  1. vLLM server starts and loads the NVFP4 model without errors
  2. Model produces coherent multi-turn conversation responses via the OpenAI-compatible API
  3. VRAM usage is measured at idle and under load at 4K, 8K, 16K, and 32K context lengths
  4. Generation throughput (tok/s), prefill speed (tok/s), and TTFT are recorded for reference
  5. Model + FP8 KV cache fits under 18GB at a usable context length (target 32K+)
**Plans**: TBD

Plans:
- [ ] 02-01: TBD

### Phase 3: TurboQuant + Verdict
**Goal**: TQ KV performance characterized, compared to baseline, go/no-go decision made with evidence
**Depends on**: Phase 2
**Requirements**: TQ-01, TQ-02, TQ-03, TQ-04, CMP-01, CMP-02, CMP-03
**Success Criteria** (what must be TRUE):
  1. vLLM starts with --kv-cache-dtype turboquant_k8v4 alongside NVFP4 weights without errors
  2. TQ KV output quality is comparable to FP8 KV (no quality collapse)
  3. VRAM savings from TQ KV are quantified at each context length vs FP8 baseline
  4. Go/no-go decision for Nexus Engine integration is documented with VRAM, throughput, and quality evidence
**Plans**: TBD

Plans:
- [ ] 03-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Environment Setup | 0/0 | Not started | - |
| 2. NVFP4 Baseline Validation | 0/0 | Not started | - |
| 3. TurboQuant + Verdict | 0/0 | Not started | - |
