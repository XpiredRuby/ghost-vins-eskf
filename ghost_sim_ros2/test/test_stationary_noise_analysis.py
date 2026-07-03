import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.stationary_noise_analysis import (  # noqa: E402
    CSV_SCHEMA,
    DETRENDING_STATUS,
    HARDWARE_STATUS,
    NOISE_ASSUMPTION_STATUS,
    NoiseAnalysisReport,
    allan_deviation,
    analyze_axis,
    analyze_pose_csv,
    autocorrelation,
    detrend_linear,
    fit_allan_slope,
    format_markdown_report,
    generate_ar1_drift_noise,
    generate_flicker_like_noise,
    generate_random_walk_noise,
    generate_white_noise,
    interpret_allan_slope,
    main,
    uniform_resample,
)


def fit_slope(taus, adevs, lo, hi):
    return fit_allan_slope(taus, adevs, lo_s=lo, hi_s=hi)


def write_pose_csv(path, t, x, y, z):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["t", "x", "y", "z"])
        writer.writeheader()
        for row in zip(t, x, y, z):
            writer.writerow({"t": row[0], "x": row[1], "y": row[2], "z": row[3]})


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
    dt = 0.1
    x = generate_white_noise(32768, std_m=1.0, seed=7)

    taus, adevs = allan_deviation(x, dt)
    slope = fit_slope(taus, adevs, lo=0.2, hi=10.0)

    assert -0.70 < slope < -0.30
    assert interpret_allan_slope(slope) == "white-noise-like"


def test_allan_deviation_identifies_random_walk_position_noise():
    dt = 0.1
    x = generate_random_walk_noise(32768, step_std_m=1.0, seed=8)

    taus, adevs = allan_deviation(x, dt)
    slope = fit_slope(taus, adevs, lo=0.2, hi=10.0)

    assert 0.30 < slope < 0.75
    assert interpret_allan_slope(slope) == "random-walk-or-drift-like"


def test_allan_deviation_identifies_flicker_like_noise_as_flat():
    dt = 0.1
    x = generate_flicker_like_noise(32768, amplitude_m=1.0, seed=12)

    taus, adevs = allan_deviation(x, dt)
    slope = fit_slope(taus, adevs, lo=0.2, hi=8.0)

    assert -0.25 <= slope <= 0.25
    assert interpret_allan_slope(slope) == "flicker-or-floor-like"


def test_ar1_generator_matches_colored_noise_expectations():
    dt = 0.1
    t = np.arange(0.0, 160.0, dt)
    x = generate_ar1_drift_noise(len(t), rho=0.985, process_std_m=0.0012, white_std_m=0.0025, seed=9)

    summary = analyze_axis("x", t, x, dt, max_lag=20, nperseg=256)

    assert summary.raw_lag1_autocorrelation > 0.50
    assert summary.raw_psd_power_below["0.50"] > 0.50
    assert summary.raw_overall_allan_class in {"flicker-or-floor-like", "random-walk-or-drift-like"}
    assert summary.lag1_autocorrelation == summary.raw_lag1_autocorrelation


def test_analyze_axis_reports_raw_and_detrended_separately():
    rng = np.random.default_rng(44)
    dt = 0.1
    t = np.arange(0.0, 80.0, dt)
    trend = 0.004 * t
    x = trend + 0.002 * np.sin(2.0 * np.pi * 0.12 * t) + rng.normal(0.0, 0.0005, len(t))

    summary = analyze_axis("x", t, x, dt, max_lag=20, nperseg=128)

    assert summary.detrending_applied
    assert abs(summary.linear_trend_slope_mps) > 0.001
    assert summary.raw_lag1_autocorrelation != summary.detrended_lag1_autocorrelation
    assert summary.raw_psd_power_below != summary.detrended_psd_power_below
    assert summary.lag1_autocorrelation == summary.raw_lag1_autocorrelation
    assert summary.overall_allan_slope == summary.raw_overall_allan_slope


def test_analyze_axis_reports_colored_noise_as_correlated():
    rng = np.random.default_rng(9)
    dt = 0.1
    t = np.arange(0.0, 80.0, dt)

    x = 0.01 * np.sin(2.0 * np.pi * 0.12 * t) + rng.normal(0.0, 0.001, len(t))
    summary = analyze_axis("x", t, x, dt, max_lag=20, nperseg=128)

    assert summary.raw_lag1_autocorrelation > 0.5
    assert summary.raw_psd_power_below["0.50"] > 0.5
    assert len(summary.raw_allan_slopes) > 0
    assert len(summary.detrended_allan_slopes) > 0


def test_analyze_pose_csv_schema_and_json_fields(tmp_path):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)
    x = generate_ar1_drift_noise(len(t), seed=20)
    y = generate_white_noise(len(t), std_m=0.001, seed=21)
    z = np.zeros_like(t)

    csv_path = tmp_path / "pose.csv"
    write_pose_csv(csv_path, t, x, y, z)

    report = analyze_pose_csv(csv_path)
    as_dict = json.loads(json.dumps(report, default=lambda o: o.__dict__))

    assert tuple(report.csv_schema) == CSV_SCHEMA
    assert report.noise_assumption_status == NOISE_ASSUMPTION_STATUS
    assert report.hardware_status == HARDWARE_STATUS
    assert report.detrending_status == DETRENDING_STATUS
    assert report.detrending_applied is True
    assert "raw_* fields" in report.comparison_guidance
    assert set(report.axes) == {"x", "y"}
    assert as_dict["csv_schema"] == list(CSV_SCHEMA)
    assert "raw_lag1_autocorrelation" in as_dict["axes"]["x"]
    assert "detrended_lag1_autocorrelation" in as_dict["axes"]["x"]


def test_cli_writes_json_and_markdown_outputs(tmp_path):
    dt = 0.1
    t = np.arange(0.0, 25.0, dt)
    x = generate_white_noise(len(t), std_m=0.001, seed=30)
    y = generate_white_noise(len(t), std_m=0.001, seed=31)
    z = np.zeros_like(t)

    csv_path = tmp_path / "pose.csv"
    write_pose_csv(csv_path, t, x, y, z)

    json_out = tmp_path / "noise_summary.json"
    md_out = tmp_path / "noise_summary.md"
    rc = main([str(csv_path), "--json-out", str(json_out), "--markdown-out", str(md_out)])

    assert rc == 0
    summary = json.loads(json_out.read_text())
    md = md_out.read_text()
    assert summary["csv_schema"] == list(CSV_SCHEMA)
    assert summary["noise_assumption_status"] == NOISE_ASSUMPTION_STATUS
    assert summary["detrending_status"] == DETRENDING_STATUS
    assert "raw_lag1_autocorrelation" in summary["axes"]["x"]
    assert "detrended_lag1_autocorrelation" in summary["axes"]["x"]
    assert "Raw diagnostics (baseline-comparable)" in md
    assert "Detrended diagnostics (drift-removed)" in md
    assert "does not assume white Gaussian noise" in md


def test_markdown_report_contains_raw_detrended_caveat():
    rng = np.random.default_rng(10)
    dt = 0.1
    t = np.arange(0.0, 30.0, dt)
    x = rng.normal(0.0, 0.001, len(t))

    x_summary = analyze_axis("x", t, x, dt, max_lag=10, nperseg=64)
    y_summary = analyze_axis("y", t, detrend_linear(t, x), dt, max_lag=10, nperseg=64)

    report = NoiseAnalysisReport(
        source="synthetic.csv",
        csv_schema=CSV_SCHEMA,
        noise_assumption_status=NOISE_ASSUMPTION_STATUS,
        white_noise_assumption_flag="WHITE_NOISE_NOT_ASSUMED_DIAGNOSTIC_ONLY",
        hardware_status=HARDWARE_STATUS,
        detrending_status=DETRENDING_STATUS,
        detrending_applied=True,
        comparison_guidance="Use raw_* fields for old baseline comparison.",
        sample_count_raw=len(t),
        sample_count_uniform=len(t),
        dt_s=dt,
        sample_rate_hz=1.0 / dt,
        axes={"x": x_summary, "y": y_summary},
    )

    md = format_markdown_report(report)

    assert "does not assume white Gaussian noise" in md
    assert "Raw diagnostics (baseline-comparable)" in md
    assert "Detrended diagnostics (drift-removed)" in md
    assert "CSV schema" in md
