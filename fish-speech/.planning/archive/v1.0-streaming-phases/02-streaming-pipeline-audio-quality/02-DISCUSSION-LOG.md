# Phase 2: Streaming Pipeline & Audio Quality - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 02-streaming-pipeline-audio-quality
**Areas discussed:** Crossfade strategy, StreamingCrossfader architecture, Streaming emission, WAV header, Audio encoding, PeakFilter ordering, Backward compatibility
**Mode:** --auto (all areas auto-selected, recommended options chosen)

---

## Crossfade Algorithm & Duration

| Option | Description | Selected |
|--------|-------------|----------|
| Equal-power sin² crossfade, 10-20ms | Industry standard for imperceptible transitions, 441-882 samples at 44.1kHz | Y |
| Linear crossfade | Simpler but causes slight energy dip at midpoint | |
| No crossfade (gap/silence insert) | Audible seams, defeats the purpose | |

**User's choice:** [auto] Equal-power sin² — research findings confirm this eliminates clicks while being computationally trivial
**Notes:** Duration aligns with DAC hop_length (512 samples = 11.6ms), providing natural boundary alignment

---

## StreamingCrossfader Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Buffer tail, blend with next head | Dedicated class buffers overlap_samples from each segment's tail, blends with next segment's head | Y |
| Full overlap-add on all segments | Traditional signal processing approach, requires all segments in memory | |
| Post-concatenation crossfade | Concatenate first, then apply crossfade at known boundaries | |

**User's choice:** [auto] Buffer tail approach — only approach compatible with streaming (segments emitted before next is generated)
**Notes:** First segment has no prior to blend with — emit after trimming tail into buffer. Last segment's tail flushed without blending.

---

## WAV Header Format

| Option | Description | Selected |
|--------|-------------|----------|
| 0xFFFFFFFF for RIFF and data sizes | WAV spec for unknown/streaming length | Y |
| Keep current 0-byte header | Works for most players but technically malformed | |
| Omit header entirely (raw PCM) | Requires client to know format a priori | |

**User's choice:** [auto] 0xFFFFFFFF — correct per WAV spec, best player compatibility for streaming
**Notes:** Simple modification to wav_chunk_header() utility function

---

## PeakFilter Ordering

| Option | Description | Selected |
|--------|-------------|----------|
| Per-chunk before crossfade (current) | Already implemented, crossfade on post-FX audio | Y |
| After crossfade | Would require restructuring, risk of double-processing | |
| Both (per-chunk + final pass) | Over-processing, unnecessary | |

**User's choice:** [auto] Keep current per-chunk — already correct, overlap region too small for FX artifacts
**Notes:** 10-20ms overlap is negligible for a mild 3500Hz peak filter

---

## Emission Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Emit ASAP after crossfade | First chunk immediate, subsequent after blending | Y |
| Buffer 2 chunks before first emit | Smoother start but higher TTFA | |
| Emit all at end | Defeats streaming purpose | |

**User's choice:** [auto] ASAP — minimizes TTFA, first chunk has no prior to crossfade with
**Notes:** Critical for meeting STRM-01 (<500ms TTFA target)

---

## Backward Compatibility

| Option | Description | Selected |
|--------|-------------|----------|
| Keep non-streaming path unchanged | CLI merges VQ codes pre-decode, no crossfade needed | Y |
| Apply crossfade to non-streaming too | Unnecessary — single decode produces seamless audio | |

**User's choice:** [auto] Keep unchanged — non-streaming path already produces seamless audio via code concatenation
**Notes:** RBST-03 requires backward compatibility

---

## Claude's Discretion

- Exact sin² crossfade implementation details
- Internal method names and StreamingCrossfader API surface
- Buffer management (pre-allocation vs dynamic)
- Logging verbosity for streaming segments

## Deferred Ideas

- Acoustic tail prompting (ADVQ-01) — v2
- Overlapped DAC decoding (ADVQ-02) — v2
- Adaptive chunk sizing (ADVQ-03) — v2
- KV cache accumulation (PERF-02) — v2
