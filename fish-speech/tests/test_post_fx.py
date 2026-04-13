"""Unit tests for HumanismPostFX audio processing chain."""

import numpy as np
import pytest

from fish_speech.utils.post_fx import HumanismPostFX, PostFXConfig

# Shared test signal: 1-second 440Hz sine wave at 44100Hz
SR = 44100
DURATION = 1.0
SAMPLES = int(SR * DURATION)
SINE_440 = np.sin(2 * np.pi * 440 * np.arange(SAMPLES) / SR).astype(np.float32)


def test_config_defaults_all_intensities_to_one():
    """PostFXConfig defaults all intensities to 1.0."""
    cfg = PostFXConfig()
    assert cfg.eq_low_intensity == 1.0
    assert cfg.eq_high_intensity == 1.0
    assert cfg.compression_intensity == 1.0
    assert cfg.deess_intensity == 1.0
    assert cfg.saturation_intensity == 1.0


def test_all_intensities_zero_produces_near_identity():
    """With all intensities at 0.0, output is nearly identical to input (only Clipping remains)."""
    cfg = PostFXConfig(
        eq_low_intensity=0.0,
        eq_high_intensity=0.0,
        compression_intensity=0.0,
        deess_intensity=0.0,
        saturation_intensity=0.0,
    )
    fx = HumanismPostFX(cfg)
    output = fx.process(SINE_440.copy(), SR)
    # Clipping at -0.1dB only affects peaks above ~0.989, sine peaks at 1.0
    # so output should be very close but not identical (clipping shaves peaks)
    assert np.allclose(output, SINE_440, atol=0.02)


def test_process_preserves_shape():
    """process() on a 44100-sample sine wave returns array of same shape."""
    fx = HumanismPostFX(PostFXConfig())
    output = fx.process(SINE_440.copy(), SR)
    assert output.shape == SINE_440.shape


def test_process_output_within_bounds():
    """process() output never exceeds [-1.0, 1.0] range (WARM-06 safety)."""
    fx = HumanismPostFX(PostFXConfig())
    # Use a hot signal that could clip
    hot_signal = (SINE_440 * 1.5).astype(np.float32)
    output = fx.process(hot_signal, SR)
    assert np.all(output >= -1.0)
    assert np.all(output <= 1.0)


def test_saturation_asymmetry():
    """Asymmetric saturation produces different output for positive vs negative half-cycles."""
    cfg = PostFXConfig(
        eq_low_intensity=0.0,
        eq_high_intensity=0.0,
        compression_intensity=0.0,
        deess_intensity=0.0,
        saturation_intensity=1.0,
    )
    fx = HumanismPostFX(cfg)
    output = fx.process(SINE_440.copy(), SR)

    positive_mask = SINE_440 > 0.1  # avoid near-zero where difference is negligible
    negative_mask = SINE_440 < -0.1

    pos_mean = np.abs(output[positive_mask]).mean()
    neg_mean = np.abs(output[negative_mask]).mean()
    # Asymmetric saturation means positive and negative means differ
    assert pos_mean != pytest.approx(neg_mean, abs=0.001)


def test_streaming_consecutive_calls_no_error():
    """process() with reset=False across two consecutive calls does not raise errors."""
    fx = HumanismPostFX(PostFXConfig())
    chunk1 = SINE_440[:SR // 2].copy()
    chunk2 = SINE_440[SR // 2:].copy()
    # First call uses reset=True internally, second uses reset=False
    out1 = fx.process(chunk1, SR)
    out2 = fx.process(chunk2, SR)
    assert out1.shape == chunk1.shape
    assert out2.shape == chunk2.shape


def test_each_intensity_zero_bypasses_effect():
    """Each intensity parameter at 0.0 bypasses its corresponding effect."""
    # Full chain
    full_cfg = PostFXConfig()
    full_fx = HumanismPostFX(full_cfg)
    full_output = full_fx.process(SINE_440.copy(), SR)

    # Test each effect can be individually turned off
    effects = [
        "eq_low_intensity",
        "eq_high_intensity",
        "compression_intensity",
        "deess_intensity",
        "saturation_intensity",
    ]
    for effect_name in effects:
        # Create config with only this effect off
        kwargs = {effect_name: 0.0}
        cfg = PostFXConfig(**kwargs)
        fx = HumanismPostFX(cfg)
        output = fx.process(SINE_440.copy(), SR)
        # Output should differ from full chain (proving the effect was active in full chain)
        assert not np.allclose(output, full_output, atol=0.001), (
            f"Disabling {effect_name} did not change output -- effect may not be active"
        )
