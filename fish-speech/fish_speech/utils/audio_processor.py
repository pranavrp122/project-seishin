"""HumanismAudioProcessor: Audio post-processor for breathing silences and volume dynamics.

Implements two audio processing features:
  1. Breathing silence insertion at cue positions (~100ms gaps with cosine ramps)
  2. Volume gain scaling at hint regions (0.85x asides, 1.1x emphasis)

Stateless position-based processing (unlike HumanismPostFX which is stateful).
Instantiated once per request. Consumes HumanismHints from TextPreprocessor.

Usage:
    from fish_speech.utils.audio_processor import HumanismAudioProcessor, AudioProcessorConfig
    from fish_speech.utils.text_preprocessor import TextPreprocessor, PreprocessorConfig

    tp = TextPreprocessor(PreprocessorConfig())
    text, hints = tp.preprocess("Hello world. This is a test.")
    proc = HumanismAudioProcessor(
        config=AudioProcessorConfig(),
        humanism_hints=hints,
        text_length=len(text),
        sample_rate=44100,
    )
    audio = proc.process_volume(audio, audio_offset_samples=0)
    audio = proc.process_breathing(audio)
"""

import random
import re
from dataclasses import dataclass

import numpy as np
from loguru import logger

from fish_speech.utils.text_preprocessor import (
    BreathingCue,
    HumanismHints,
    VolumeHint,
)


@dataclass
class AudioProcessorConfig:
    """Configuration for HumanismAudioProcessor feature toggles."""

    enable_breathing: bool = True
    enable_volume: bool = True
    silence_duration_ms: float = 100.0  # 80-150ms range (D-04), 100ms default
    aside_gain: float = 0.85  # D-08
    emphasis_gain: float = 1.1  # D-08
    ramp_duration_ms: float = 20.0  # D-10


class HumanismAudioProcessor:
    """Audio post-processor for breathing silences and volume dynamics.

    Stateless position-based processing (unlike HumanismPostFX which was stateful).
    Instantiated once per request. Consumes HumanismHints from TextPreprocessor.

    Breathing: inserts silence gaps (~100ms) at BreathingCue positions (D-04).
    Volume: applies gain scaling (0.85x aside, 1.1x emphasis) at VolumeHint regions (D-08).
    """

    def __init__(
        self,
        config: AudioProcessorConfig,
        humanism_hints: HumanismHints,
        text_length: int,
        sample_rate: int,
    ) -> None:
        self._config = config
        self._hints = humanism_hints
        self._text_length = text_length
        self._sample_rate = sample_rate
        self._ramp_samples = int(sample_rate * config.ramp_duration_ms / 1000)
        # Roll breathing cue probabilities once at init (D-05, Pitfall 4)
        self._active_breathing_offsets: list[int] = self._roll_breathing_cues()
        # Track cumulative silence insertion offset for position correction
        self._cumulative_insertion_samples = 0

    # -------------------------------------------------------------------
    # Breathing cue selection
    # -------------------------------------------------------------------

    def _roll_breathing_cues(self) -> list[int]:
        """Roll probability for each BreathingCue, enforce max 1 per ~4 sentences.

        Returns list of accepted char_offsets where breathing silences will be
        inserted. Rolled once at init to avoid per-segment randomness (D-05).
        """
        cues = self._hints.breathing_cues
        if not cues:
            return []

        # Count sentences for spacing (BRVL-02: max 1 per 3-5 sentences)
        text = self._hints.original_text
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        sentence_count = max(1, len(sentences))
        max_breathing = max(1, sentence_count // 4)  # ~1 per 4 sentences

        accepted: list[int] = []
        for cue in cues:
            if len(accepted) >= max_breathing:
                break
            if random.random() < cue.probability:
                accepted.append(cue.char_offset)

        logger.debug(
            "Breathing cues: {}/{} accepted (max {} for {} sentences)",
            len(accepted),
            len(cues),
            max_breathing,
            sentence_count,
        )
        return accepted

    # -------------------------------------------------------------------
    # Position mapping
    # -------------------------------------------------------------------

    @staticmethod
    def _char_to_sample(
        char_offset: int, text_length: int, audio_length_samples: int
    ) -> int:
        """Map a character offset to a sample position via linear interpolation.

        Assumes roughly uniform character-to-time ratio (D-14).
        """
        if text_length <= 0:
            return 0
        ratio = char_offset / text_length
        return int(ratio * audio_length_samples)

    # -------------------------------------------------------------------
    # Volume processing (streaming-safe, no length change)
    # -------------------------------------------------------------------

    def process_volume(
        self, audio: np.ndarray, audio_offset_samples: int
    ) -> np.ndarray:
        """Apply volume dynamics to a segment. Does NOT change array length.

        Safe to call during streaming. Maps VolumeHint char regions to sample
        positions and applies gain with cosine ramps to prevent clicks.

        Args:
            audio: Float32 mono audio segment.
            audio_offset_samples: Sample offset of this segment in the full audio.

        Returns:
            Volume-adjusted audio (same length as input).
        """
        if not self._config.enable_volume or not self._hints.volume_hints:
            return audio

        audio = audio.copy()  # Don't mutate input
        seg_start = audio_offset_samples
        seg_end = audio_offset_samples + len(audio)
        applied_count = 0

        for hint in self._hints.volume_hints:
            hint_start = self._char_to_sample(
                hint.char_offset, self._text_length, seg_end
            )
            hint_end = self._char_to_sample(
                hint.char_offset + hint.char_length, self._text_length, seg_end
            )
            # Check overlap with current segment
            region_start = max(0, hint_start - seg_start)
            region_end = min(len(audio), hint_end - seg_start)
            if region_end > region_start:
                self._apply_gain_region(audio, region_start, region_end, hint.gain)
                applied_count += 1

        # Safety clip after all gain ops (Pitfall 3)
        np.clip(audio, -1.0, 1.0, out=audio)

        if applied_count > 0:
            logger.debug(
                "Volume: applied {} gain regions to segment at offset {}",
                applied_count,
                audio_offset_samples,
            )
        return audio

    def _apply_gain_region(
        self, audio: np.ndarray, start: int, end: int, gain: float
    ) -> None:
        """Apply gain to a region with cosine ramp transitions. Modifies in-place.

        Ramp in:  smoothly transitions from 1.0 to target gain.
        Ramp out: smoothly transitions from target gain back to 1.0.
        """
        ramp = min(self._ramp_samples, (end - start) // 2)  # Clamp ramp to half region
        if ramp < 1:
            audio[start:end] *= gain
            return

        # Ramp in: 1.0 -> gain
        t = np.linspace(0, np.pi / 2, ramp, dtype=np.float32)
        ramp_in = 1.0 + (gain - 1.0) * np.sin(t) ** 2
        audio[start : start + ramp] *= ramp_in

        # Flat region
        audio[start + ramp : end - ramp] *= gain

        # Ramp out: gain -> 1.0
        ramp_out = gain + (1.0 - gain) * np.sin(t) ** 2
        audio[end - ramp : end] *= ramp_out

    # -------------------------------------------------------------------
    # Breathing processing (final audio only, changes length)
    # -------------------------------------------------------------------

    def process_breathing(self, audio: np.ndarray) -> np.ndarray:
        """Insert breathing silence gaps into complete audio. Changes array length.

        Call on final concatenated audio, NOT during streaming (Pitfall 2).
        Processes in reverse order to avoid position shifting (Pitfall 1).

        Args:
            audio: Float32 mono audio (complete, post-crossfade).

        Returns:
            Audio with silence gaps inserted at breathing cue positions.
        """
        if not self._config.enable_breathing or not self._active_breathing_offsets:
            return audio

        sr = self._sample_rate
        silence_samples = int(sr * self._config.silence_duration_ms / 1000)
        ramp = self._ramp_samples

        # Process in reverse order to avoid position shifting (Pitfall 1)
        for char_off in reversed(self._active_breathing_offsets):
            pos = self._char_to_sample(char_off, self._text_length, len(audio))
            pos = max(ramp, min(len(audio) - ramp, pos))
            audio = self._insert_silence(audio, pos, silence_samples, ramp)

        logger.debug(
            "Breathing: inserted {} silence gaps (~{}ms each)",
            len(self._active_breathing_offsets),
            self._config.silence_duration_ms,
        )
        return audio

    def _insert_silence(
        self, audio: np.ndarray, pos: int, silence_samples: int, ramp: int
    ) -> np.ndarray:
        """Insert silence gap with cosine ramps at the given sample position.

        Applies fade-out before the gap and fade-in after, preventing clicks.

        Args:
            audio: Full audio array.
            pos: Sample position to insert the silence.
            silence_samples: Number of silence samples to insert.
            ramp: Number of samples for fade-out/fade-in ramps.

        Returns:
            New audio array with silence inserted (longer than input).
        """
        t = np.linspace(0, np.pi / 2, ramp, dtype=np.float32)
        fade_out = np.cos(t) ** 2  # 1.0 -> 0.0
        fade_in = np.sin(t) ** 2  # 0.0 -> 1.0

        before = audio[:pos].copy()
        after = audio[pos:].copy()

        if len(before) >= ramp:
            before[-ramp:] *= fade_out
        if len(after) >= ramp:
            after[:ramp] *= fade_in

        silence = np.zeros(silence_samples, dtype=np.float32)
        return np.concatenate([before, silence, after])
