"""HumanismPostFX: Professional vocal post-processing chain for TTS output.

Implements a 6-stage audio processing chain:
  1. De-ess (narrow notch at 6.5kHz) - WARM-04
  2. Low-shelf EQ at 250Hz (warmth/body) - WARM-01
  3. High-shelf EQ at 8kHz (air/shimmer) - WARM-02
  4. Compression (gentle 2:1) - WARM-03
  5. Asymmetric saturation (even-harmonic warmth) - WARM-05
  6. Safety clipper at -0.1dB (prevents clipping) - WARM-06

Each effect (except the safety clipper) has a 0.0-1.0 intensity parameter.
At 0.0 the effect is bypassed; at 1.0 it is fully engaged.

Usage:
    from fish_speech.utils.post_fx import HumanismPostFX, PostFXConfig

    fx = HumanismPostFX(PostFXConfig())  # all defaults at 1.0
    processed = fx.process(audio_chunk, sample_rate=44100)
"""

from dataclasses import dataclass

import numpy as np
from pedalboard import (
    Clipping,
    Compressor,
    HighShelfFilter,
    LowShelfFilter,
    PeakFilter,
    Pedalboard,
)


@dataclass
class PostFXConfig:
    """Per-effect intensity controls (0.0 = bypass, 1.0 = full effect).

    WARM-06 (safety clipper) is always on with no intensity knob.
    """

    eq_low_intensity: float = 1.0  # WARM-01: 0.0=flat, 1.0=+3dB at 250Hz
    eq_high_intensity: float = 1.0  # WARM-02: 0.0=flat, 1.0=+2dB at 8kHz
    compression_intensity: float = 1.0  # WARM-03: 0.0=1:1, 1.0=2:1 ratio
    deess_intensity: float = 1.0  # WARM-04: 0.0=flat, 1.0=-6dB at 6.5kHz
    saturation_intensity: float = 1.0  # WARM-05: 0.0=clean, 1.0=full drive


class HumanismPostFX:
    """Professional vocal post-processing chain for TTS output.

    Creates a per-request stateful audio processor. The pedalboard chain
    maintains IIR filter state across consecutive process() calls (streaming),
    with reset=True only on the first call to clear any stale state.

    Chain order: De-ess -> EQ low -> EQ high -> Compress -> [Clip] -> Saturate -> [np.clip]
    """

    def __init__(self, config: PostFXConfig) -> None:
        self._config = config
        self._board = self._build_board(config)
        self._first_call = True

    def _build_board(self, cfg: PostFXConfig) -> Pedalboard:
        """Build pedalboard chain from config intensities.

        Effects with intensity 0.0 are omitted from the chain entirely.
        The safety Clipping plugin is always included.
        """
        plugins = []

        # 1. De-ess: narrow notch at 6.5kHz (WARM-04)
        if cfg.deess_intensity > 0:
            plugins.append(
                PeakFilter(
                    cutoff_frequency_hz=6500,
                    gain_db=cfg.deess_intensity * -6.0,  # 0.0=flat, 1.0=-6dB
                    q=4.0,
                )
            )

        # 2. Low-shelf EQ: warmth at 250Hz (WARM-01)
        if cfg.eq_low_intensity > 0:
            plugins.append(
                LowShelfFilter(
                    cutoff_frequency_hz=250,
                    gain_db=cfg.eq_low_intensity * 3.0,  # 0.0=flat, 1.0=+3dB
                    q=0.7,
                )
            )

        # 3. High-shelf EQ: air at 8kHz (WARM-02)
        if cfg.eq_high_intensity > 0:
            plugins.append(
                HighShelfFilter(
                    cutoff_frequency_hz=8000,
                    gain_db=cfg.eq_high_intensity * 2.0,  # 0.0=flat, 1.0=+2dB
                    q=0.7,
                )
            )

        # 4. Compression (WARM-03)
        if cfg.compression_intensity > 0:
            plugins.append(
                Compressor(
                    threshold_db=-20.0,
                    ratio=1.0 + cfg.compression_intensity * 1.0,  # 0.0=1:1, 1.0=2:1
                    attack_ms=10.0,
                    release_ms=100.0,
                )
            )

        # 5. Safety clipper at -0.1dB (WARM-06) -- always on
        plugins.append(Clipping(threshold_db=-0.1))

        return Pedalboard(plugins)

    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Process a single audio chunk through the full FX chain.

        Maintains pedalboard IIR filter state across consecutive calls
        for streaming compatibility (WARM-07). First call uses reset=True
        to clear any stale state; subsequent calls use reset=False.

        Args:
            audio: Float32 mono audio array, expected range [-1.0, 1.0].
            sample_rate: Sample rate in Hz (typically 44100).

        Returns:
            Processed audio as float32 array, guaranteed within [-1.0, 1.0].
        """
        # Pedalboard processing (de-ess, EQ, compress, clip)
        reset = self._first_call
        self._first_call = False
        processed = self._board.process(audio, sample_rate, reset=reset)

        # Saturation (numpy, outside pedalboard chain) (WARM-05)
        if self._config.saturation_intensity > 0:
            processed = self._apply_saturation(processed, self._config.saturation_intensity)

        # Final safety clip (redundant guard after saturation)
        return np.clip(processed, -1.0, 1.0)

    def _apply_saturation(self, audio: np.ndarray, intensity: float) -> np.ndarray:
        """Asymmetric soft saturation for even-harmonic warmth (WARM-05).

        Positive half-cycle: tanh(drive * x) -- symmetric, odd harmonics only.
        Negative half-cycle: tanh(drive * x) + k * x^2 -- adds even harmonics.

        The quadratic term on negative half-cycles breaks odd-symmetry of tanh,
        introducing 2nd and 4th harmonics that mimic tube/transformer coloration.

        Args:
            audio: Input audio array.
            intensity: Saturation intensity (0.0=clean, 1.0=full drive).

        Returns:
            Saturated audio array.
        """
        drive = 1.0 + intensity * 2.0  # range [1.0, 3.0]
        k = intensity * 0.1  # quadratic asymmetry coefficient, range [0.0, 0.1]

        driven = drive * audio
        saturated = np.tanh(driven)

        # Add quadratic asymmetry only to negative half-cycles
        mask = audio < 0
        saturated[mask] += k * audio[mask] ** 2

        return saturated
