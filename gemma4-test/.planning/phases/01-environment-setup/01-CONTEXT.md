# Phase 1: Environment Setup - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up a working Docker environment that can launch vLLM with NVFP4 Gemma 4 support on RTX 5090. Download the model, pull/build Docker images, and verify the container starts correctly.

</domain>

<decisions>
## Implementation Decisions

### Docker Strategy
- **D-01:** Two-stage Docker approach. Stage 1: pre-built `vllm/vllm-openai:gemma4-cu130` image with patch mount for baseline. Stage 2: Python overlay Dockerfile on top of base image for TurboQuant (avoids full CUDA rebuild).
- **D-02:** Model stored at `~/models/gemma4-26b-a4b-nvfp4`. Downloaded via `huggingface-cli download`.
- **D-03:** `gemma4_patched.py` mounted as read-only volume replacing stock vLLM Gemma 4 model file at `/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py`.

### vLLM Source
- **D-04:** TurboQuant source from `Alberto-Codes/vllm` branch `feat/gemma4-heterogeneous-tq`. This branch is based on vibhavagarwal5's PR #38479 with Gemma 4 heterogeneous head_dim support.
- **D-05:** Overlay Dockerfile copies only changed Python + Triton files (no C++/CUDA compilation needed). Faster build, depends on base image vLLM version compatibility.

### Environment
- **D-06:** All flags locked: `--quantization modelopt`, `--moe-backend marlin`, `--kv-cache-dtype fp8` (baseline) / `turboquant_k8v4` (TQ), `--max-model-len 32768`, `--max-num-seqs 1`, `--gpu-memory-utilization 0.92`.
- **D-07:** Environment variables: `VLLM_NVFP4_GEMM_BACKEND=marlin`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, `VLLM_WORKER_MULTIPROC_METHOD=spawn`.

### Claude's Discretion
- Fallback behavior when Docker image tags don't exist (scripts already try multiple tags)
- Container naming, port selection (8000 is set)
- Wait timeout for server readiness (5 min is set)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Research Documents
- `gemma4-test/RESEARCH-VLLM-SETUP.md` -- Step-by-step vLLM setup guide with Docker commands, flag explanations, troubleshooting
- `gemma4-test/RESEARCH.md` -- Main research: NVFP4 model details, architecture, KV cache analysis
- `gemma4-test/RESEARCH-NVFP4-TQ-COMPAT.md` -- NVFP4 + TurboQuant compatibility proof, code path analysis
- `gemma4-test/RESEARCH-TQ-PLUGIN.md` -- TQ plugin analysis (why plugin path was rejected)

### Existing Scripts
- `gemma4-test/setup.sh` -- Model download + Docker image setup (both stages)
- `gemma4-test/run.sh` -- Container launch commands (baseline and TQ modes)
- `gemma4-test/test.sh` -- Test script (Phase 2)
- `gemma4-test/benchmark.sh` -- Benchmark script (Phase 2)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `setup.sh` -- Complete model download + Docker image build pipeline with error handling
- `run.sh` -- Complete container launch with preflight checks, health polling, log tailing

### Established Patterns
- Two-stage approach (baseline first, TQ second) is baked into both scripts
- Image tag stored in `.baseline-image` / `.tq-image` dotfiles for cross-script coordination
- Color-coded logging with info/warn/error helpers

### Integration Points
- Container exposes OpenAI-compatible API on port 8000
- Health check at `/health`, metrics at `/metrics`
- Model mounted read-only from `~/models/`

</code_context>

<specifics>
## Specific Ideas

No specific requirements -- scripts already encode all decisions from prior conversation. Execute setup.sh stages in order and verify container starts.

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 01-environment-setup*
*Context gathered: 2026-04-14*
