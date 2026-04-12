<!-- GSD:project-start source:PROJECT.md -->
## Project

**Streaming Chunked Audio for Fish Speech S2-Pro**

A streaming audio emission system for Fish Speech S2-Pro TTS that splits text into small chunks, generates audio per chunk, and emits audio as soon as each chunk is ready. Reduces time-to-first-audio (TTFA) from ~1.5s to <500ms while maintaining the current audio quality and emotional consistency.

**Core Value:** Users hear the first audio within 500ms of submitting text, with no perceivable quality loss or choppiness at chunk boundaries.

### Constraints

- **Quality**: No perceivable degradation vs current non-streaming output
- **Architecture**: Must work within existing inference pipeline (no model retraining)
- **VRAM**: Must not exceed current 10.7GB peak
- **Compatibility**: Must preserve torch.compile reduce-overhead + INT8 quantization
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Executive Summary
## Existing Stack (Already in Codebase)
| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| numpy | 2.4.4 | Audio array manipulation, crossfade math | Installed, actively used |
| soundfile | 0.13.1 | WAV file I/O, in-memory buffer writes | Installed, used in views.py |
| pedalboard | 0.9.22 | Post-processing EQ (PeakFilter at 3500Hz) | Installed, used in engine |
| torch | 2.8.0+cu128 | DAC decoder inference, tensor ops | Installed, core dependency |
| Python `wave` | stdlib | WAV header generation | Used in utils.py |
| Python `io` | stdlib | BytesIO for in-memory WAV buffering | Used in utils.py and views.py |
| kui (asgi) | - | HTTP server, StreamResponse | Installed, serving layer |
## New Components Needed (Zero New Dependencies)
### 1. Hann Window Crossfade
| Aspect | Detail |
|--------|--------|
| **What** | Smooth blending at chunk audio boundaries to eliminate clicks/pops |
| **Implementation** | Pure numpy -- 10 lines of code |
| **Confidence** | HIGH -- identical approach used in Qwen3-TTS-streaming (production) |
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Overlap samples | 1024 | ~23ms at 44.1kHz. Qwen3-TTS uses 512 at 24kHz (~21ms). Scale proportionally. Start here, tune down if latency-sensitive. |
| Min overlap | 512 | ~11.6ms. Below this, crossfade becomes too short to mask discontinuities. |
| Max overlap | 2048 | ~46ms. Beyond this, crossfade wastes audio and adds latency. |
- Tapers smoothly to zero at edges with zero-slope endpoints
- Satisfies the Constant Overlap-Add (COLA) constraint -- two overlapping Hann windows sum to 1.0
- Standard in STFT and audio processing (not novel or risky)
- The fade_in + fade_out = 1.0 property means no energy gain or loss at the boundary
- Linear crossfade: Energy dip at midpoint (sounds like a brief volume drop)
- No crossfade (just concatenate): Clicks and pops at boundaries -- this is the current problem
- Overlap-add with FFT convolution: Overkill for simple boundary blending; that's for FIR filtering
### 2. DAC Decoder Overlap Context
| Aspect | Detail |
|--------|--------|
| **What** | Feed extra context tokens to the DAC decoder beyond the current chunk |
| **Implementation** | Slice management in the decode loop |
| **Confidence** | MEDIUM -- DAC is causal so forward-context isn't needed, but the convolutional receptive field still benefits from left context |
- Prepend the last N context tokens from the previous chunk when decoding
- Discard the audio corresponding to context tokens
- Emit only the new chunk's audio (after crossfade with previous tail)
- Default context: 4-8 tokens (~46-93ms). DAC's own chunked decode uses 10% overlap.
### 3. WAV Streaming Header
| Aspect | Detail |
|--------|--------|
| **What** | Modified WAV header for unknown-length chunked HTTP streaming |
| **Implementation** | Modify existing `wav_chunk_header()` in utils.py |
| **Confidence** | HIGH -- standard technique, already partially implemented |
- Signals to decoders "length unknown, read until EOF"
- Confirmed working with Whisper, browser `<audio>` elements, and most audio players
- The existing 44-byte header structure stays the same
| Parameter | Value | Why |
|-----------|-------|-----|
| Sample rate | 44100 Hz | DAC model's native rate (`self.sample_rate = 44100`) |
| Bit depth | 16-bit | PCM_16 -- standard for streaming, matches `AMPLITUDE = 32768` scaling in inference.py |
| Channels | 1 (mono) | Single speaker, as specified in PROJECT.md |
| Encoding | PCM (AudioFormat=1) | Uncompressed, lowest latency, no codec overhead |
### 4. Streaming Protocol
| Aspect | Detail |
|--------|--------|
| **What** | HTTP chunked transfer encoding for audio delivery |
| **Implementation** | Already exists via kui's `StreamResponse` |
| **Confidence** | HIGH -- already working in the codebase |
| Factor | Chunked HTTP | WebSocket |
|--------|-------------|-----------|
| Already implemented | Yes (StreamResponse in views.py) | No |
| Text available upfront | Yes (single TTS request) | Unnecessary |
| Bidirectional needed | No (no mid-utterance control) | Overkill |
| Infrastructure complexity | None (standard HTTP) | Connection management, heartbeats |
| Client compatibility | Universal | Requires WebSocket client |
## Recommended Stack (Complete)
### Core (Already Installed -- No Changes)
| Technology | Version | Purpose | Why This |
|------------|---------|---------|----------|
| numpy | 2.4.4 | Crossfade math, audio array ops | Already used everywhere. Hann window is 3 numpy calls. No reason to add scipy. |
| soundfile | 0.13.1 | WAV I/O, buffer writes | Already used in views.py for non-streaming. Supports `sf.SoundFile` objects for incremental writes. |
| pedalboard | 0.9.22 | Post-FX (PeakFilter) | Already in the pipeline. Apply per-chunk, not per-final-audio. |
| torch | 2.8.0+cu128 | DAC decoding | Core inference engine. `from_indices()` for VQ decode. |
| Python `wave` | stdlib | WAV header generation | Already used. Modify header bytes directly for streaming length field. |
| Python `io.BytesIO` | stdlib | In-memory audio buffering | Already used throughout. |
### Supporting (Already Installed -- No Changes)
| Technology | Version | Purpose | Why This |
|------------|---------|---------|----------|
| kui (ASGI) | (installed) | HTTP server with StreamResponse | Already serves the /v1/tts endpoint with chunked streaming |
| loguru | (installed) | Logging | Already used throughout inference engine |
| ormsgpack | (installed) | Binary serialization | Already used for API responses |
### What NOT to Install
| Library | Why NOT |
|---------|---------|
| scipy | Only needed for `scipy.signal.fftconvolve` (overlap-add filtering) which is irrelevant here. Hann crossfade is trivially done in numpy. Adding scipy for 3 lines of math is wasteful. |
| pydub | Full-file loading into memory, no real-time support, dependency on ffmpeg. Completely wrong tool for streaming. |
| pyaudio / sounddevice | For local audio playback. This is a server -- audio goes over HTTP, not to speakers. |
| librosa | Already avoided in inference path (only used in dataset loading). Heavy dependency with lazy imports. |
| streaming-tts (PyPI) | Wrapper around cloud TTS APIs. We're building the TTS server, not consuming one. |
| RealtimeTTS | Same -- consumer-side library for playing TTS output. |
| scikit-maad | The `crossfade` utility is for offline batch processing. Numpy does this in 3 lines. |
## Chunk Size Strategy
| Chunk Size | Tokens (~) | Audio Duration (~) | Latency Impact | Quality Impact |
|------------|-----------|-------------------|----------------|----------------|
| 100 bytes | 40-60 | 0.5-0.7s | Low TTFA, many boundaries | More crossfade points, higher artifact risk |
| 200 bytes | 80-120 | 1.0-1.4s | Good TTFA | Good balance |
| 512 bytes (default) | 200-300 | 2.3-3.5s | High TTFA | Fewest boundaries, best quality |
| Tokens | Audio Samples | Duration | Notes |
|--------|--------------|----------|-------|
| 20 | 10,240 | 232ms | Too granular, decode overhead dominates |
| 50 | 25,600 | 580ms | Reasonable minimum for DAC decode |
| 86 (~1s) | 44,100 | 1000ms | Good balance |
| Full chunk | Varies | Varies | Current behavior (decode entire text chunk at once) |
## Architecture Implications
## Sources
### Verified (HIGH confidence)
- Fish Speech codebase: `fish_speech/inference_engine/`, `fish_speech/models/dac/modded_dac.py`, `tools/server/`
- [NumPy 2.4.4 on PyPI](https://pypi.org/project/numpy/) -- verified installed version
- [soundfile 0.13.1 documentation](https://python-soundfile.readthedocs.io/)
- [Pedalboard v0.9.22](https://pypi.org/project/pedalboard/)
- [WAV File Format Specification](http://soundfile.sapp.org/doc/WaveFormat/)
### Production references (MEDIUM confidence -- different codebases but same patterns)
- [Qwen3-TTS-streaming](https://github.com/rekuenkdr/Qwen3-TTS-streaming) -- Hann crossfade at 512 samples/24kHz, two-phase streaming
- [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts) -- Sliding window decode with 25-frame left context
- [DAC chunked decoding](https://github.com/descriptinc/descript-audio-codec/issues/101) -- 10% overlap for boundary smoothing
- [Deepgram: WebSocket vs REST for TTS](https://deepgram.com/learn/websocket-vs-rest-text-to-speech)
### Protocol references (HIGH confidence)
- [HTTP Streaming vs WebSocket comparison](https://dev.to/mechcloud_academy/streaming-http-vs-websocket-vs-sse-a-comparison-for-real-time-data-1geo)
- [Fish Audio Real-time Streaming docs](https://docs.fish.audio/developer-guide/best-practices/real-time-streaming)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
