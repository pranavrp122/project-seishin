"""Benchmark TTFA, RTF, and VRAM for streaming vs non-streaming inference."""

import time
import sys
import numpy as np
import torch
from loguru import logger

from tools.server.model_manager import ModelManager
from fish_speech.utils.schema import ServeTTSRequest
from tools.server.inference import inference_wrapper

CHECKPOINT = "checkpoints/s2-pro"
CODEC = "checkpoints/s2-pro/codec.pth"
DEVICE = "cuda"

TEST_TEXTS = {
    "short": "Hello, how are you doing today?",
    "medium": "The quick brown fox jumps over the lazy dog. It was a beautiful sunny morning, and the birds were singing in the trees.",
    "long": (
        "In the heart of the ancient forest, where sunlight barely penetrated the thick canopy above, "
        "a narrow path wound its way between towering oaks and whispering pines. The air was cool and "
        "damp, carrying the scent of moss and fallen leaves. Somewhere in the distance, a stream "
        "murmured over smooth stones, its gentle song blending with the rustle of branches overhead. "
        "A deer paused at the edge of a clearing, ears twitching, before bounding silently into the "
        "undergrowth. This was a place untouched by time, where nature held dominion over all."
    ),
}


def measure_vram():
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        return torch.cuda.max_memory_allocated() / 1024**3
    return 0.0


def run_benchmark(engine, text, streaming, label, warmup=False):
    req = ServeTTSRequest(
        text=text,
        references=[],
        reference_id=None,
        max_new_tokens=1024,
        chunk_length=200,
        top_p=0.7,
        repetition_penalty=1.2,
        temperature=0.7,
        streaming=streaming,
        seed=42,
        format="wav",
    )

    torch.cuda.reset_peak_memory_stats()
    t_start = time.perf_counter()
    t_first_audio = None
    total_bytes = 0
    chunk_count = 0
    header_received = False

    for chunk in inference_wrapper(req, engine):
        if isinstance(chunk, bytes):
            if not header_received and len(chunk) == 44:
                # WAV header
                header_received = True
                continue
            if t_first_audio is None:
                t_first_audio = time.perf_counter()
            total_bytes += len(chunk)
            chunk_count += 1
        elif isinstance(chunk, np.ndarray):
            # Batch mode: final result is a float32 numpy array
            if t_first_audio is None:
                t_first_audio = time.perf_counter()
            total_bytes += len(chunk) * 2  # float32 -> int16 would be 2 bytes/sample
            chunk_count += 1

    t_end = time.perf_counter()
    vram_peak = measure_vram()

    # int16 = 2 bytes/sample, 44100 Hz
    total_samples = total_bytes // 2
    audio_duration = total_samples / 44100.0
    wall_time = t_end - t_start
    ttfa = (t_first_audio - t_start) if t_first_audio else wall_time
    rtf = wall_time / audio_duration if audio_duration > 0 else float("inf")

    if not warmup:
        mode = "STREAM" if streaming else "BATCH "
        print(f"\n{'='*60}")
        print(f"  {label} [{mode}]")
        print(f"{'='*60}")
        print(f"  Text length:    {len(text)} chars")
        print(f"  Audio duration: {audio_duration:.2f}s")
        print(f"  Wall time:      {wall_time:.3f}s")
        print(f"  TTFA:           {ttfa*1000:.0f}ms {'<-- TARGET <500ms' if streaming else ''}")
        print(f"  RTF:            {rtf:.3f}x {'(< 1.0 = faster than realtime)' if rtf < 1.0 else ''}")
        print(f"  Chunks:         {chunk_count}")
        print(f"  Peak VRAM:      {vram_peak:.2f} GB")
        print(f"{'='*60}")

    return {
        "label": label,
        "streaming": streaming,
        "text_len": len(text),
        "audio_sec": audio_duration,
        "wall_sec": wall_time,
        "ttfa_ms": ttfa * 1000,
        "rtf": rtf,
        "chunks": chunk_count,
        "vram_gb": vram_peak,
    }


def main():
    print("Loading model...")
    t0 = time.perf_counter()
    manager = ModelManager(
        mode="tts",
        device=DEVICE,
        half=False,
        compile=True,
        llama_checkpoint_path=CHECKPOINT,
        decoder_checkpoint_path=CODEC,
        decoder_config_name="modded_dac_vq",
    )
    engine = manager.tts_inference_engine
    print(f"Model loaded + warmed up in {time.perf_counter()-t0:.1f}s\n")

    # Extra warmup runs (torch.compile needs a few runs)
    print("Warmup runs (torch.compile)...")
    for _ in range(2):
        run_benchmark(engine, "Warmup sentence one two three.", True, "warmup", warmup=True)
        run_benchmark(engine, "Warmup sentence one two three.", False, "warmup", warmup=True)
    print("Warmup done.\n")

    results = []
    for name, text in TEST_TEXTS.items():
        for streaming in [True, False]:
            r = run_benchmark(engine, text, streaming, name)
            results.append(r)

    # Summary table
    print("\n" + "=" * 80)
    print(f"  {'Test':<10} {'Mode':<8} {'Chars':>5} {'Audio':>7} {'Wall':>7} {'TTFA':>8} {'RTF':>6} {'Chunks':>6} {'VRAM':>7}")
    print("-" * 80)
    for r in results:
        mode = "stream" if r["streaming"] else "batch"
        print(
            f"  {r['label']:<10} {mode:<8} {r['text_len']:>5} "
            f"{r['audio_sec']:>6.2f}s {r['wall_sec']:>6.2f}s "
            f"{r['ttfa_ms']:>6.0f}ms {r['rtf']:>5.3f} "
            f"{r['chunks']:>6} {r['vram_gb']:>6.2f}G"
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
