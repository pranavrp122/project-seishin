# Gemma 4 26B-A4B NVFP4 + TurboQuant KV Test

## What This Is

An independent test environment for evaluating Gemma 4 26B-A4B with NVFP4 weight quantization and TurboQuant KV cache compression on an RTX 5090 32GB under WSL2. The goal is to validate that the model + KV cache fits under 18GB VRAM before integrating into the Nexus Engine voice companion pipeline as a replacement for Qwen 3.5 9B.

## Core Value

Prove Gemma 4 26B-A4B fits under 18GB VRAM (model + KV) with acceptable quality and throughput on RTX 5090, leaving headroom for Fish Speech and Parakeet containers.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Build vLLM from PR #38479 (TurboQuant native backend) with Alberto-Codes' Gemma 4 fixes
- [ ] Run Gemma 4 NVFP4 via Docker with correct environment for RTX 5090/SM120
- [ ] Measure actual VRAM usage (model weights + KV cache) at various context lengths
- [ ] Verify model + KV fits under 18GB at usable context lengths
- [ ] Test TurboQuant KV compression (TQ4 keys + FP8 values) on top of NVFP4 weights
- [ ] Benchmark throughput (tokens/sec generation, prefill speed)
- [ ] Validate output quality (coherent multi-turn conversation, instruction following)
- [ ] Compare NVFP4+FP8 KV baseline vs NVFP4+TQ KV for VRAM savings and quality

### Out of Scope

- Pipeline integration with Nexus Engine — separate project after validation
- Fish Speech / Parakeet container testing — those are paused during this test
- Multi-user / concurrent request serving — single-user test only
- Multimodal (image/audio) inputs — text-only evaluation
- llama.cpp path — decided on vLLM for speed prioritization (NVFP4 CUDA kernels not implemented in llama.cpp)
- MXFP4-MOE format — decided on NVFP4 for native FP4 tensor core support on Blackwell

## Context

- **Model**: `bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4` — 15.7GB weights, MoE architecture (128 experts, 8 active, 3.8B active params)
- **Architecture**: Hybrid attention — 5 global layers (head_dim=512, 4 KV heads, full context) + 25 sliding window layers (head_dim=256, 4 KV heads, 1024-token window)
- **vLLM source**: vibhavagarwal5/vllm fork with TurboQuant native backend (PR #38479), plus Alberto-Codes' Gemma 4 fixes (PRs #4 and #6)
- **Key insight**: KV cache is NOT the primary VRAM bottleneck — only 5 global layers scale with context. Sliding window layers cap at 1024 tokens regardless.
- **NVFP4 + TQ compatibility**: Confirmed independent code paths. Weight quant and KV quant dispatch separately via `DISPATCH_BY_KV_CACHE_DTYPE`. `TQFullAttentionSpec` with `next_power_of_2` padding fixes page alignment.
- **Critical setup**: `gemma4_patched.py` needed for NVFP4 MoE scale key mapping, `--moe-backend marlin`, CUDA 13.0 Docker image (cu130)
- **Prior work**: 5 research documents completed covering NVFP4 setup, TQ plugin compatibility, llama.cpp analysis, vLLM setup guide, and NVFP4+TQ compatibility proof

## Constraints

- **VRAM budget**: Model + KV must fit under 18GB (leaving 14GB for Fish Speech + Parakeet on shared 32GB RTX 5090)
- **Hardware**: RTX 5090 32GB, SM120/Blackwell, WSL2, CUDA 13.2, Driver 595.79
- **No local CUDA**: No nvcc/CUDA toolkit installed — must use Docker for everything
- **Single GPU**: No tensor parallelism, single-device inference only
- **Single user**: `--max-num-seqs 1` — companion pipeline serves one user

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| vLLM over llama.cpp | NVFP4 CUDA kernels not implemented in llama.cpp (Issue #21777); vLLM has native support | -- Pending |
| NVFP4 over MXFP4-MOE | Native FP4 tensor cores on Blackwell, speed priority. MXFP4-MOE is 13.7GB but uses MXFP4 format | -- Pending |
| PR #38479 fork build | TurboQuant native backend not yet merged to vLLM main; Alberto-Codes has Gemma 4 hybrid fixes | -- Pending |
| Docker-based setup | No local CUDA/nvcc available in WSL2 environment | -- Pending |
| TQ4 keys + FP8 values | Best quality/compression ratio (~2.66x) per research; head_dim=512 on global layers is untested | -- Pending |
| 18GB VRAM target | Must leave room for Fish Speech (~5GB) + Parakeet (~4.5GB) + OS overhead on 32GB card | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-14 after initialization*
