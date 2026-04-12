---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 4 research starting
last_updated: "2026-04-12T09:30:00.000Z"
last_activity: 2026-04-12 -- Phase 4 added, phases 1-3 marked complete
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 0
  completed_plans: 0
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-12)

**Core value:** Optimize Fish Speech S2-Pro for efficient single-GPU inference with minimal VRAM and fastest RTF without quality loss
**Current focus:** Phase 4 - Experimental Optimizations

## Current Position

Phase: 4 of 4 (Experimental Optimizations)
Plan: 0 of 0 in current phase (research-first, plans TBD)
Status: Starting research
Last activity: 2026-04-12 -- Phase 4 added, phases 1-3 marked complete

Progress: [███████░░░] 75%

## Stable Baseline

**Tag:** stable-v1.0
**Branch:** stable-backup
**Commit:** 487e2f9
**Metrics:** VRAM 9.2GB | RTF 0.263x | Presence EQ + tuned gen params
**Restore:** `git checkout stable-backup` to revert any experimental changes

## Performance Metrics

**Current stable build:**

| Metric | Value |
|--------|-------|
| VRAM (idle) | 8.88 GB |
| VRAM (generating) | 9.2-9.9 GB |
| RTF (mean) | 0.263x |
| RTF (range) | 0.245x - 0.294x |
| Sample rate | 44.1 kHz |
| Quantization | INT8 W8A16 |
| Compile mode | reduce-overhead |
| Precision | BF16 + TF32 matmul |

## Accumulated Context

### Decisions

- Soundfile replaces torchaudio.load (crashes on certain formats)
- INT8 W8A16 chosen for best VRAM/quality tradeoff
- DAC mask 4096x4096 sufficient for inference lengths
- TF32 matmul precision for free 10-15% speed
- Presence EQ (3.5kHz +1.5dB) for crispness, full pedalboard chain rejected
- Gen params tuned: temp=0.875, rep=1.05, chunk=350

### Pending Todos

- Research cutting-edge optimization techniques
- Test each in isolation against stable baseline
- Document results in CHANGES.md

### Blockers/Concerns

- PyTorch 2.10+ has 40-55% throughput regression in reduce-overhead mode (pytorch/pytorch#174575)
- SM120/Blackwell kernel support is immature across the ecosystem
- Must not degrade voice quality for any speed/VRAM gain

## Session Continuity

Last session: 2026-04-12
Stopped at: Phase 4 research starting
Resume file: None
