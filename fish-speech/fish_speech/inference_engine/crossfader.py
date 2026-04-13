"""Streaming crossfader with equal-power sin² blending for chunk boundaries.

Buffers overlap regions between consecutive audio segments and applies
equal-power crossfade (sin²/cos²) to eliminate clicks and discontinuities
at chunk boundaries during streaming TTS inference.
"""

import numpy as np


class StreamingCrossfader:
    """Stateful crossfader that blends overlapping regions between audio segments.

    Equal-power crossfade ensures constant energy through the transition:
        fade_in  = sin(t * pi/2)²
        fade_out = cos(t * pi/2)²
        fade_in + fade_out = 1.0 at every sample (trig identity)

    Usage:
        cf = StreamingCrossfader(overlap_samples=1764)  # 40ms at 44.1kHz
        for segment in audio_segments:
            output = cf.process(segment)
            if output is not None:
                yield output
        tail = cf.flush()
        if tail is not None:
            yield tail
    """

    def __init__(self, overlap_samples: int = 1764):
        self._overlap = overlap_samples
        self._tail_buffer: np.ndarray | None = None

        # Precompute fade curves (float32 for direct multiplication with audio)
        t = np.linspace(0, 1, overlap_samples, dtype=np.float32)
        self._fade_in = np.sin(t * np.pi / 2) ** 2
        self._fade_out = np.cos(t * np.pi / 2) ** 2

    def process(self, segment: np.ndarray) -> np.ndarray | None:
        """Process a segment, blending with buffered tail from the previous segment.

        First call: returns body (segment minus tail), buffers tail.
        Subsequent calls: blends buffered tail with segment head, returns
        blended + body, buffers new tail.

        Args:
            segment: Float32 numpy array of audio samples from get_audio_segment().

        Returns:
            Crossfaded audio output, or None if the entire segment was buffered.
        """
        if len(segment) < self._overlap:
            # Segment too short for proper crossfade — emit what we can
            if self._tail_buffer is not None:
                result = np.concatenate([self._tail_buffer, segment])
                self._tail_buffer = None
                return result
            return segment

        if self._tail_buffer is None:
            # First segment: emit body, buffer tail
            body = segment[:-self._overlap]
            self._tail_buffer = segment[-self._overlap:].copy()
            return body if len(body) > 0 else None

        # Subsequent segment: blend tail with head, emit blended + body, buffer new tail
        head = segment[:self._overlap]
        blended = self._tail_buffer * self._fade_out + head * self._fade_in

        body = segment[self._overlap:-self._overlap]
        self._tail_buffer = segment[-self._overlap:].copy()

        if len(body) > 0:
            return np.concatenate([blended, body])
        return blended

    def flush(self) -> np.ndarray | None:
        """Emit the remaining buffered tail after all segments are processed.

        Returns:
            The buffered tail samples, or None if no tail is buffered.
        """
        if self._tail_buffer is not None:
            tail = self._tail_buffer
            self._tail_buffer = None
            return tail
        return None
