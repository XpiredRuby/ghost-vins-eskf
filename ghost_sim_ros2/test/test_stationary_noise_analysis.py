import math
import sys
from pathlib import Path

import numpy as np

# Keep the tests runnable both through `pip install .` and directly from a
# source checkout in GitHub Actions or a ROS workspace.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.stationary_noise_analysis import (  # noqa: E402
    NoiseAnalysisReport,
    allan_deviation,
    analyze_axis,
    autocorrelation,
    detrend_linear,
    format_markdown_report,
    interpret_allan_slope,
    uniform_resample,
)


def fit_slope(taus, adevs, lo, hi):
    mask = (taus >= lo) & (taus <= hi) & (adevs > 0.0)
    assert int(np.sum(mask)) >= 4
    return float(np.polyfit(np.log10(taus[mask]), np.log10(adevs[mask]), 1)[0])


def test_uniform_resample_recovers_requested_dt():
    t = np.array([0.0, 0.09, 0.21, 0.30, 0.41])
    x = np.sin(t)
    tu, xu, dt = uniform_resample(t, x, dt_s=0.1)

    assert math.isclose(dt, 0.1)
    assert math.isclose(tu[0], 0.0, abs_tol=1e-12)
    assert len(tu) >= 5
    assert np.all(np.isfinite(xu))


def test_autocorrelation_lag_zero_is_one():
    x = np.arange(100, dtype=float)
    acf = autocorrelation(x, max_lag=10)

    assert math.isclose(float(acf[0]), 1.0)
    assert len(acf) == 11


def test_allan_deviation_identifies_white_position_noise():
    rng = np.random.default_rng(7)
    dt = 0.1
    x = rng.normal(0.0, 1.0, 16384)

    taus, adevs = allan_deviation(x, dt)
    slope = fit_slope(taus, adevs, lo=0.2, hi=10.0)

    assert -0.85 < slope < -0.15
    assert interpret_allan_slope(slope) == "white-noise-like"


def test_allan_deviation_identifies_random_walk_position_noise():
    rng = np.random.default_rng(8)
    dt = 0.1
    x = np.cumsum(rng.normal(0.0, 1.0, 16384)) * math.sqrt(dt)

    taus, adevs = allan_deviation(x, dt)
    slope = fit_slope(taus, adevs, lo=0.2, hi=10.0)

    assert 0.15 < slope < 0.95
    assert interpret_allan_slope(slope) == "random-walk-or-drift-like"


def test_analyze_axis_reports_colored_noise_as_correlated():
    rng = np.random.default_rng(9)
    dt = 0.1
    t = np.arange(0.0, 80.0, dt)

    # Synthetic colored/drift-like signal: slow sinusoid + small white noise.
    x = 0.01 * np.sin(2.0 * np.pi * 0.12 * t) + rng.normal(0.0, 0.001, len(t))
    summary = analyze_axis("x", t, x, dt, max_lag=20, nperseg=128)

    assert summary.lag1_autocorrelation > 0.5
    assert summary.psd_power_below["0.50"] > 0.5
    assert len(summary.allan_slopes) > 0


def test_markdown_report_contains_white_noise_caveat():
    rng = np.random.default_rng(10)
    dt = 0.1
    t = np.arange(0.0, 30.0, dt)
    x = rng.normal(0.0, 0.001, len(t))

    x_summary = analyze_axis("x", t, x, dt, max_lag=10, nperseg=64)
    y_summary = analyze_axis("y", t, detrend_linear(t, x), dt, max_lag=10, nperseg=64)

    report = NoiseAnalysisReport(
        source="synthetic.csv",
        sample_count_raw=len(t),
        sample_count_uniform=len(t),
        dt_s=dt,
        sample_rate_hz=1.0 / dt,
        axes={"x": x_summary, "y": y_summary},
    )

    md = format_markdown_report(report)

    assert "does not assume white Gaussian noise" in md
    assert "Stationary AprilTag Noise Characterization" in md
