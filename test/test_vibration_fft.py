"""
test_vibration_fft.py — Unit tests for FFT conversion and ArduPilot vibration analysis functions.
"""
import pytest
import numpy as np
from uavlogviewer.tools.vibration_fft import (
    compute_fft,
    extract_fft_segment,
    compute_ap_vibration,
    compute_ap_vibration_3d
)


def test_compute_fft_sine_wave():
    """Test FFT computation on a pure sine wave with known frequency and amplitude."""
    fs = 100.0  # 100 Hz sampling rate
    duration = 5.0
    t = np.arange(0, duration, 1.0 / fs)
    f0 = 15.0  # 15 Hz signal
    amp = 2.5
    y = amp * np.sin(2.0 * np.pi * f0 * t) + 10.0  # with DC offset

    freqs, mags = compute_fft(y, fs)

    assert len(freqs) == len(mags)
    assert freqs[0] == 0.0
    # Peak should be very close to 15 Hz
    peak_idx = np.argmax(mags)
    assert abs(freqs[peak_idx] - f0) < 0.5
    # Hanning window reduces peak amplitude by 0.5 when normalized by N/2 (as in single_log_vibration_analysis.py)
    assert abs(mags[peak_idx] - (amp * 0.5)) < 0.1


def test_extract_fft_segment_continuous():
    """Test extracting continuous segment from uniform timestamps."""
    t = np.linspace(0, 10, 1000)
    y = np.sin(t)
    seg_t, seg_y, fs = extract_fft_segment(t, y, mode="longest")
    assert len(seg_t) == 1000
    assert len(seg_y) == 1000
    assert abs(fs - 100.0) < 1.0


def test_extract_fft_segment_with_gaps():
    """Test extracting longest segment when data contains a large gap."""
    # First segment: 200 samples, dt = 0.01s (2 seconds)
    t1 = np.arange(0, 2.0, 0.01)
    y1 = np.ones_like(t1)
    # Gap: jump from 2.0 to 100.0
    # Second segment: 500 samples, dt = 0.01s (5 seconds) - longest!
    t2 = np.arange(100.0, 105.0, 0.01)
    y2 = np.ones_like(t2) * 2

    t = np.concatenate([t1, t2])
    y = np.concatenate([y1, y2])

    seg_t, seg_y, fs = extract_fft_segment(t, y, mode="all")
    # Should automatically pick the longest segment (t2, 500 samples)
    assert len(seg_t) == len(t2)
    assert abs(seg_t[0] - 100.0) < 1e-4
    assert abs(fs - 100.0) < 1.0


def test_compute_ap_vibration_dc_signal():
    """Test ArduPilot vibration calculation on constant signal (no vibration)."""
    t = np.arange(0, 5.0, 0.005)  # 200 Hz
    y = np.full_like(t, 9.81)    # Constant 1G

    vibe = compute_ap_vibration(y, t)
    assert len(vibe) == len(y)
    # After initial transient, vibration on constant signal should decay to zero
    assert np.all(vibe[-100:] < 0.05)


def test_compute_ap_vibration_ac_signal():
    """Test ArduPilot vibration calculation on signal with high-frequency noise."""
    fs = 200.0
    t = np.arange(0, 10.0, 1.0 / fs)
    # DC component (constant 9.8) + AC vibration (30 Hz sine wave amplitude 3.0 m/s^2)
    y = 9.8 + 3.0 * np.sin(2.0 * np.pi * 30.0 * t)

    vibe = compute_ap_vibration(y, t)
    assert len(vibe) == len(y)
    # RMS of sine with amplitude A is A / sqrt(2) = 3.0 / 1.414 = 2.12
    # In steady state, ArduPilot vibration filter measures RMS vibration level
    steady_vibe = vibe[int(3.0 * fs):]  # After 3 seconds transient
    mean_vibe = np.mean(steady_vibe)
    assert 1.5 < mean_vibe < 2.5


def test_compute_ap_vibration_3d():
    """Test 3D composite vibration computation."""
    fs = 200.0
    t = np.arange(0, 5.0, 1.0 / fs)
    x = 1.0 * np.sin(2.0 * np.pi * 25.0 * t)
    y = 2.0 * np.sin(2.0 * np.pi * 25.0 * t)
    z = 9.8 + 2.0 * np.sin(2.0 * np.pi * 25.0 * t)

    vx, vy, vz, vmag = compute_ap_vibration_3d(x, y, z, t)
    assert len(vx) == len(t)
    assert len(vy) == len(t)
    assert len(vz) == len(t)
    assert len(vmag) == len(t)

    # Magnitude must equal sqrt(vx^2 + vy^2 + vz^2)
    expected_mag = np.sqrt(vx**2 + vy**2 + vz**2)
    np.testing.assert_allclose(vmag, expected_mag, rtol=1e-5)
