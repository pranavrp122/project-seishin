"""Tests for StreamingCrossfader equal-power sin² crossfade blending."""

import numpy as np
import pytest

from fish_speech.inference_engine.crossfader import StreamingCrossfader


class TestFirstSegment:
    """First segment emits body immediately, buffers tail."""

    def test_first_segment_emits_body_buffers_tail(self):
        cf = StreamingCrossfader(overlap_samples=100)
        segment = np.ones(1000, dtype=np.float32)
        result = cf.process(segment)

        assert result is not None
        assert len(result) == 900  # 1000 - 100 overlap buffered as tail

    def test_first_segment_tail_available_via_flush(self):
        cf = StreamingCrossfader(overlap_samples=100)
        segment = np.ones(1000, dtype=np.float32)
        cf.process(segment)
        tail = cf.flush()

        assert tail is not None
        assert len(tail) == 100
        np.testing.assert_array_equal(tail, np.ones(100, dtype=np.float32))


class TestSubsequentSegments:
    """Subsequent segments blend buffered tail with current head."""

    def test_subsequent_segment_blends_and_buffers(self):
        cf = StreamingCrossfader(overlap_samples=100)
        seg1 = np.ones(1000, dtype=np.float32)
        seg2 = np.ones(1000, dtype=np.float32) * 0.5

        r1 = cf.process(seg1)
        r2 = cf.process(seg2)
        r3 = cf.flush()

        assert r1 is not None
        assert r2 is not None
        assert r3 is not None
        assert len(r1) == 900   # body of first segment
        assert len(r2) == 900   # 100 blended + 800 body
        assert len(r3) == 100   # final tail

    def test_blend_math_is_correct(self):
        """Verify the exact crossfade math at known points.

        For seg1=all 1.0 and seg2=all 0.5:
        blended[i] = 1.0 * cos²(t*pi/2) + 0.5 * sin²(t*pi/2)
        At t=0: 1.0*1.0 + 0.5*0.0 = 1.0
        At t=0.5: 1.0*0.5 + 0.5*0.5 = 0.75
        At t=1.0: 1.0*0.0 + 0.5*1.0 = 0.5
        """
        cf = StreamingCrossfader(overlap_samples=100)
        seg1 = np.ones(1000, dtype=np.float32)
        seg2 = np.ones(1000, dtype=np.float32) * 0.5

        cf.process(seg1)
        r2 = cf.process(seg2)

        # The first 100 samples of r2 are the blended region
        blended = r2[:100]

        # t=0 (first sample): should be ~1.0 (all from seg1 tail)
        assert abs(blended[0] - 1.0) < 1e-6

        # t≈0.5 (middle sample): should be ~0.75
        mid = len(blended) // 2
        assert abs(blended[mid] - 0.75) < 0.02  # slight tolerance for discrete sampling

        # t=1.0 (last sample): should be ~0.5 (all from seg2 head)
        assert abs(blended[-1] - 0.5) < 1e-6


class TestFlush:
    """flush() returns buffered tail or None."""

    def test_flush_returns_tail(self):
        cf = StreamingCrossfader(overlap_samples=100)
        segment = np.ones(1000, dtype=np.float32) * 3.0
        cf.process(segment)
        tail = cf.flush()

        assert tail is not None
        assert len(tail) == 100
        np.testing.assert_allclose(tail, np.full(100, 3.0, dtype=np.float32))

    def test_flush_when_empty(self):
        cf = StreamingCrossfader(overlap_samples=100)
        result = cf.flush()
        assert result is None

    def test_flush_clears_buffer(self):
        cf = StreamingCrossfader(overlap_samples=100)
        cf.process(np.ones(1000, dtype=np.float32))
        cf.flush()
        # Second flush should return None
        assert cf.flush() is None


class TestEnergyConservation:
    """Equal-power crossfade: sin²(t) + cos²(t) = 1.0 at every sample."""

    def test_energy_conservation(self):
        overlap = 200
        cf = StreamingCrossfader(overlap_samples=overlap)

        # Access the internal fade curves to verify the identity
        energy = cf._fade_in + cf._fade_out
        np.testing.assert_allclose(energy, np.ones(overlap), atol=1e-7)

    def test_energy_conservation_default_overlap(self):
        """Verify with default 1764-sample overlap (40ms at 44.1kHz)."""
        cf = StreamingCrossfader()  # default 1764
        energy = cf._fade_in + cf._fade_out
        np.testing.assert_allclose(energy, np.ones(1764), atol=1e-7)


class TestTotalSamplesPreserved:
    """N segments of L samples -> total = N*L - (N-1)*overlap."""

    def test_total_samples_preserved(self):
        overlap = 100
        cf = StreamingCrossfader(overlap_samples=overlap)
        N = 5
        L = 1000

        outputs = []
        for i in range(N):
            segment = np.ones(L, dtype=np.float32) * (i + 1)
            result = cf.process(segment)
            if result is not None:
                outputs.append(result)

        tail = cf.flush()
        if tail is not None:
            outputs.append(tail)

        total = sum(len(o) for o in outputs)
        expected = N * L - (N - 1) * overlap
        assert total == expected, f"Expected {expected}, got {total}"

    def test_total_samples_two_segments(self):
        overlap = 100
        cf = StreamingCrossfader(overlap_samples=overlap)
        seg1 = np.ones(1000, dtype=np.float32)
        seg2 = np.ones(1000, dtype=np.float32) * 0.5

        r1 = cf.process(seg1)
        r2 = cf.process(seg2)
        r3 = cf.flush()

        total = len(r1) + len(r2) + len(r3)
        assert total == 2000 - 100  # 1900


class TestEdgeCases:
    """Edge cases: short segments, exact overlap-length segments."""

    def test_short_segment_no_crash(self):
        cf = StreamingCrossfader(overlap_samples=100)
        short = np.ones(50, dtype=np.float32)
        # Should not crash
        result = cf.process(short)
        assert result is not None  # short segment, no tail yet -> returned as-is

    def test_short_segment_after_normal(self):
        cf = StreamingCrossfader(overlap_samples=100)
        cf.process(np.ones(1000, dtype=np.float32))
        # Now process a short segment (shorter than overlap)
        short = np.ones(50, dtype=np.float32) * 2.0
        result = cf.process(short)
        # Should concatenate tail + short and return (can't do proper crossfade)
        assert result is not None
        assert len(result) == 150  # 100 (tail) + 50 (short segment)

    def test_segment_exactly_double_overlap(self):
        """200-sample segment with overlap=100: blended only, no body."""
        cf = StreamingCrossfader(overlap_samples=100)
        seg1 = np.ones(1000, dtype=np.float32)
        seg2 = np.ones(200, dtype=np.float32) * 0.5

        cf.process(seg1)
        r2 = cf.process(seg2)

        # With 200 samples and overlap=100:
        # head = seg2[:100], body = seg2[100:100] (empty), tail = seg2[-100:]
        # Return is just the blended region (100 samples)
        assert r2 is not None
        assert len(r2) == 100  # only blended, no body

    def test_segment_exactly_overlap_length_first(self):
        """First segment with length == overlap: body is empty, returns None, buffers all."""
        cf = StreamingCrossfader(overlap_samples=100)
        segment = np.ones(100, dtype=np.float32)
        result = cf.process(segment)
        # body = segment[:-100] = empty, so returns None
        assert result is None

        # But tail should be buffered
        tail = cf.flush()
        assert tail is not None
        assert len(tail) == 100
