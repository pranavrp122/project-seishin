"""Integration smoke tests for streaming and non-streaming audio paths.

Tests the WAV header and crossfader wiring work together correctly.
These tests do NOT require a running model -- they test components
in isolation and verify the contract between them.
"""

import struct

import numpy as np

from fish_speech.inference_engine.crossfader import StreamingCrossfader
from fish_speech.inference_engine.utils import wav_chunk_header

AMPLITUDE = 32768


def test_wav_header_streaming_sizes():
    h = wav_chunk_header(sample_rate=44100, bit_depth=16, channels=1)
    assert len(h) == 44
    assert h[4:8] == b'\xff\xff\xff\xff'   # RIFF size
    assert h[40:44] == b'\xff\xff\xff\xff'  # data size
    assert h[0:4] == b'RIFF'
    assert h[8:12] == b'WAVE'


def test_wav_header_format_fields():
    h = wav_chunk_header(sample_rate=44100, bit_depth=16, channels=1)
    # Parse fmt chunk
    audio_format = struct.unpack_from('<H', h, 20)[0]
    num_channels = struct.unpack_from('<H', h, 22)[0]
    sample_rate_parsed = struct.unpack_from('<I', h, 24)[0]
    byte_rate = struct.unpack_from('<I', h, 28)[0]
    block_align = struct.unpack_from('<H', h, 32)[0]
    bits_per_sample = struct.unpack_from('<H', h, 34)[0]
    assert audio_format == 1  # PCM
    assert num_channels == 1
    assert sample_rate_parsed == 44100
    assert byte_rate == 88200  # 44100 * 1 * 2
    assert block_align == 2    # 1 * 2
    assert bits_per_sample == 16


def test_crossfader_output_compatible_with_int16_conversion():
    cf = StreamingCrossfader(overlap_samples=100)
    seg = np.random.uniform(-1.0, 1.0, 5000).astype(np.float32)
    result = cf.process(seg)
    assert result is not None
    assert result.dtype == np.float32
    int16_bytes = (result * AMPLITUDE).astype(np.int16).tobytes()
    assert len(int16_bytes) == len(result) * 2  # 2 bytes per int16 sample
    tail = cf.flush()
    assert tail is not None
    assert tail.dtype == np.float32


def test_streaming_crossfade_full_sequence():
    cf = StreamingCrossfader(overlap_samples=882)
    segments = [np.random.uniform(-1.0, 1.0, 10000).astype(np.float32) for _ in range(5)]
    outputs = []
    for seg in segments:
        out = cf.process(seg)
        if out is not None and len(out) > 0:
            outputs.append(out)
            assert out.dtype == np.float32
    tail = cf.flush()
    if tail is not None:
        outputs.append(tail)
    total_out = sum(len(o) for o in outputs)
    total_in = sum(len(s) for s in segments)
    expected = total_in - 4 * 882  # 5 segments, 4 boundaries, 882 overlap each
    assert total_out == expected, f'{total_out} != {expected}'


def test_non_streaming_path_no_crossfade():
    segments = [np.random.uniform(-1.0, 1.0, 10000).astype(np.float32) for _ in range(3)]
    audio = np.concatenate(segments, axis=0)
    assert len(audio) == 30000
    assert audio.dtype == np.float32
    # Verify no data lost -- raw concatenation preserves all samples
    np.testing.assert_array_equal(audio[:10000], segments[0])
    np.testing.assert_array_equal(audio[10000:20000], segments[1])
