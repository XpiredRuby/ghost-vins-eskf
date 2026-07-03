"""Stationary AprilTag pose noise characterization utilities for GHOST V1.

This module is pure Python/NumPy and intentionally hardware-independent. It
analyzes CSV logs with schema ``t,x,y,z`` and reports autocorrelation, Welch PSD,
and Allan deviation after resampling onto a uniform time grid.

Important estimator caveat:
These diagnostics do not assume the pose noise is white. If later code chooses
to use white-Gaussian measurement covariance, that assumption must be stated
separately and validated against these colored-noise diagnostics.

Raw vs detrended diagnostics:
Raw autocorrelation/PSD/Allan fields are preserved for direct comparison to the
earlier uncontrolled baseline. Detrended diagnostics are reported alongside them
as a drift-removed view. Do not compare detrended values to old raw baselines.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

import numpy as np

CSV_SCHEMA = ("t", "x", "y", "z")
NOISE_ASSUMPTION_STATUS = "DOES_NOT_ASSUME_WHITE_NOISE"
WHITE_NOISE_ASSUMPTION_FLAG = "WHITE_NOISE_NOT_ASSUMED_DIAGNOSTIC_ONLY"
HARDWARE_STATUS = "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"
DETRENDING_STATUS = "RAW_BASELINE_COMPARABLE_AND_DETRENDED_DIAGNOSTICS_REPORTED"

SlopeClass = Literal["white-noise-like", "flicker-or-floor-like", "random-walk-or-drift-like"]


@dataclass(frozen=True)
class AxisNoiseSummary:
    axis: str
    sample_count: int
    dt_s: float
    sample_rate_hz: float
    mean_m: float
    std_m: float
    detrended_std_m: float
    linear_trend_slope_mps: float
    detrending_applied: bool

    # Baseline-comparable raw diagnostics. These are also mirrored by the
    # legacy field names below so existing callers naturally compare raw-to-raw.
    raw_lag1_autocorrelation: float
    raw_decorrelation_time_s: float | None
    raw_psd_power_below: dict[str, float]
    raw_dominant_peaks_hz: list[dict[str, float]]
    raw_allan_selected: list[dict[str, float]]
    raw_allan_slopes: list[dict[str, float | str]]
    raw_overall_allan_slope: float
    raw_overall_allan_class: SlopeClass

    # Drift-removed diagnostics. Use these for improved characterization after
    # raw baseline comparisons have been made.
    detrended_lag1_autocorrelation: float
    detrended_decorrelation_time_s: float | None
    detrended_psd_power_below: dict[str, float]
    detrended_dominant_peaks_hz: list[dict[str, float]]
    detrended_allan_selected: list[dict[str, float]]
    detrended_allan_slopes: list[dict[str, float | str]]
    detrended_overall_allan_slope: float
    detrended_overall_allan_class: SlopeClass

    # Legacy/public aliases intentionally remain raw, not detrended, so PR #20
    # output can be compared directly to earlier uncontrolled raw baseline
    # numbers such as sigma_x=0.0355 m and lag-1 rho_x=0.995.
    lag1_autocorrelation: float
    decorrelation_time_s: float | None
    psd_power_below: dict[str, float]
    dominant_peaks_hz: list[dict[str, float]]
    allan_selected: list[dict[str, float]]
    allan_slopes: list[dict[str, float | str]]
    overall_allan_slope: float
    overall_allan_class: SlopeClass


@dataclass(frozen=True)
class NoiseAnalysisReport:
    source: str
    csv_schema: tuple[str, str, str, str]
    noise_assumption_status: str
    white_noise_assumption_flag: str
    hardware_status: str
    detrending_status: str
    detrending_applied: bool
    comparison_guidance: str
    sample_count_raw: int
    sample_count_uniform: int
    dt_s: float
    sample_rate_hz: float
    axes: dict[str, AxisNoiseSummary]


def load_pose_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load a stationary pose CSV with columns exactly compatible with ``t,x,y,z``.

    Extra columns are allowed, but the required schema must be present. The
    returned time vector is sorted and normalized to start at zero seconds.
    """
    rows: list[tuple[float, float, float, float]] = []
    with Path(path).expanduser().open(newline="") as f:
        reader = csv.DictReader(f)
        required = set(CSV_SCHEMA)
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"CSV must contain columns {list(CSV_SCHEMA)}; got {reader.fieldnames}")
        for row in reader:
            rows.append((float(row["t"]), float(row["x"]), float(row["y"]), float(row["z"])))

    if len(rows) < 8:
        raise ValueError("Need at least eight pose samples for noise analysis.")

    rows.sort(key=lambda r: r[0])
    t = np.asarray([r[0] for r in rows], dtype=float)
    t = t - t[0]
    return (
        t,
        np.asarray([r[1] for r in rows], dtype=float),
        np.asarray([r[2] for r in rows], dtype=float),
        np.asarray([r[3] for r in rows], dtype=float),
    )


def uniform_resample(t: np.ndarray, values: np.ndarray, dt_s: float | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """Linearly resample one axis onto a uniform time grid."""
    t = np.asarray(t, dtype=float)
    values = np.asarray(values, dtype=float)

    if len(t) != len(values):
        raise ValueError("t and values must have the same length.")
    if len(t) < 4:
        raise ValueError("Need at least four samples to resample.")
    if not np.all(np.diff(t) >= 0.0):
        order = np.argsort(t)
        t = t[order]
        values = values[order]

    diffs = np.diff(t)
    good_diffs = diffs[diffs > 0.0]
    if len(good_diffs) == 0:
        raise ValueError("Timestamps must contain positive time differences.")

    dt = float(np.median(good_diffs) if dt_s is None else dt_s)
    if dt <= 0.0 or not math.isfinite(dt):
        raise ValueError(f"Invalid dt: {dt}")

    t_uniform = np.arange(t[0], t[-1] + 0.5 * dt, dt)
    values_uniform = np.interp(t_uniform, t, values)
    return t_uniform - t_uniform[0], values_uniform, dt


def linear_trend(t: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    """Return best-fit slope/intercept for one time series."""
    if len(values) < 2:
        return 0.0, float(np.mean(values)) if len(values) else 0.0
    slope, intercept = np.polyfit(t, values, 1)
    return float(slope), float(intercept)


def detrend_linear(t: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Remove the best-fit line from a time series."""
    slope, intercept = linear_trend(t, values)
    return values - (slope * t + intercept)


def autocorrelation(values: np.ndarray, max_lag: int = 50) -> np.ndarray:
    """Normalized autocorrelation from lag 0 through max_lag."""
    x = np.asarray(values, dtype=float) - float(np.mean(values))
    if np.allclose(x, 0.0):
        out = np.zeros(max_lag + 1, dtype=float)
        out[0] = 1.0
        return out

    corr = np.correlate(x, x, mode="full")
    corr = corr[corr.size // 2 :]
    corr = corr / corr[0]
    return corr[: max_lag + 1]


def decorrelation_time(acf: np.ndarray, dt_s: float, threshold: float = 1.0 / math.e) -> float | None:
    """First time where autocorrelation drops below threshold."""
    below = np.where(acf < threshold)[0]
    if len(below) == 0:
        return None
    return float(below[0] * dt_s)


def welch_psd(values: np.ndarray, fs_hz: float, nperseg: int = 256, overlap: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Compute a simple Welch PSD estimate using only NumPy.

    The DC bin is zeroed intentionally because the report focuses on fluctuation
    structure rather than static pose offset. The implementation mirrors the
    common SciPy Welch form closely enough for relative power/peak diagnostics
    without adding a SciPy dependency to the Pi path.
    """
    x = np.asarray(values, dtype=float) - float(np.mean(values))
    n = len(x)
    if n < 4:
        raise ValueError("Need at least four samples for PSD.")

    seg_len = min(int(nperseg), n)
    step = max(1, int(seg_len * (1.0 - overlap)))
    window = np.hanning(seg_len)
    scale = fs_hz * float(np.sum(window**2))
    psds: list[np.ndarray] = []

    for start in range(0, n - seg_len + 1, step):
        seg = x[start : start + seg_len] * window
        spec = np.fft.rfft(seg)
        psds.append((np.abs(spec) ** 2) / scale)

    if not psds:
        seg = x * np.hanning(n)
        spec = np.fft.rfft(seg)
        psd = (np.abs(spec) ** 2) / (fs_hz * float(np.sum(np.hanning(n) ** 2)))
    else:
        psd = np.mean(np.vstack(psds), axis=0)

    freqs = np.fft.rfftfreq(seg_len, d=1.0 / fs_hz)
    if len(psd):
        psd[0] = 0.0
    return freqs, psd


def psd_power_fractions(freqs: np.ndarray, psd: np.ndarray, cutoffs_hz: Iterable[float]) -> dict[str, float]:
    """Return fraction of PSD power below each cutoff."""
    total = float(np.sum(psd))
    out: dict[str, float] = {}
    for cutoff in cutoffs_hz:
        frac = float(np.sum(psd[freqs <= cutoff]) / total) if total > 0.0 else math.nan
        out[f"{cutoff:.2f}"] = frac
    return out


def dominant_psd_peaks(freqs: np.ndarray, psd: np.ndarray, count: int = 6) -> list[dict[str, float]]:
    """Return dominant local PSD peaks.

    If no strict local maxima exist, the function intentionally falls back to
    the largest non-DC bins. That makes monotonic/smooth spectra still produce a
    useful reviewable summary, though it may return fewer than ``count`` peaks.
    """
    total = float(np.sum(psd))
    if total <= 0.0:
        return []

    local_maxima: list[int] = []
    for i in range(1, len(psd) - 1):
        if freqs[i] > 0.0 and psd[i] >= psd[i - 1] and psd[i] >= psd[i + 1]:
            local_maxima.append(i)

    candidates = local_maxima if local_maxima else [i for i in range(1, len(psd)) if freqs[i] > 0.0]
    candidates = sorted(candidates, key=lambda i: float(psd[i]), reverse=True)[:count]
    return [{"frequency_hz": float(freqs[i]), "relative_power": float(psd[i] / total)} for i in candidates]


def allan_deviation(values: np.ndarray, dt_s: float, points: int = 48) -> tuple[np.ndarray, np.ndarray]:
    """Overlapping Allan deviation for position-like data.

    For position white noise, slope is near -1/2.
    For position flicker/floor-like noise, slope is near 0.
    For position random walk/drift, slope is near +1/2.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < 8:
        raise ValueError("Need at least eight samples for Allan deviation.")

    max_m = max(2, n // 8)
    ms = np.unique(np.logspace(0, math.log10(max_m), points).astype(int))

    taus: list[float] = []
    adevs: list[float] = []
    for m in ms:
        if 2 * m >= n:
            continue
        kernel = np.ones(m, dtype=float) / float(m)
        averaged = np.convolve(x, kernel, mode="valid")
        diffs = averaged[m:] - averaged[:-m]
        if len(diffs) == 0:
            continue
        avar = 0.5 * float(np.mean(diffs**2))
        taus.append(float(m * dt_s))
        adevs.append(math.sqrt(max(avar, 0.0)))

    return np.asarray(taus, dtype=float), np.asarray(adevs, dtype=float)


def interpret_allan_slope(slope: float) -> SlopeClass:
    """Interpret Allan deviation slope into the classes used by GHOST reports."""
    if slope < -0.25:
        return "white-noise-like"
    if slope <= 0.25:
        return "flicker-or-floor-like"
    return "random-walk-or-drift-like"


def fit_allan_slope(taus: np.ndarray, adevs: np.ndarray, lo_s: float | None = None, hi_s: float | None = None) -> float:
    """Fit one log-log Allan slope over a selected tau window."""
    if len(taus) < 3:
        return math.nan
    lo = float(np.min(taus[taus > 0.0]) if lo_s is None else lo_s)
    hi = float(np.max(taus) if hi_s is None else hi_s)
    mask = (taus >= lo) & (taus <= hi) & (adevs > 0.0)
    if int(np.sum(mask)) < 3:
        return math.nan
    return float(np.polyfit(np.log10(taus[mask]), np.log10(adevs[mask]), 1)[0])


def allan_slopes_by_octave(taus: np.ndarray, adevs: np.ndarray) -> list[dict[str, float | str]]:
    """Fit local log-log slopes over adjacent octave-wide tau windows."""
    out: list[dict[str, float | str]] = []
    if len(taus) < 4:
        return out

    min_tau = float(np.min(taus[taus > 0.0]))
    max_tau = float(np.max(taus))
    lo = min_tau

    while lo * 2.0 <= max_tau * 1.001:
        hi = lo * 2.0
        mask = (taus >= lo) & (taus <= hi) & (adevs > 0.0)
        if int(np.sum(mask)) >= 2:
            slope = float(np.polyfit(np.log10(taus[mask]), np.log10(adevs[mask]), 1)[0])
            out.append(
                {
                    "tau_start_s": lo,
                    "tau_end_s": hi,
                    "slope": slope,
                    "interpretation": interpret_allan_slope(slope),
                }
            )
        lo = hi

    return out


def selected_allan_points(taus: np.ndarray, adevs: np.ndarray, targets_s: Iterable[float]) -> list[dict[str, float]]:
    """Return Allan deviation values closest to target averaging times."""
    if len(taus) == 0:
        return []
    out: list[dict[str, float]] = []
    for target in targets_s:
        idx = int(np.argmin(np.abs(taus - target)))
        out.append({"tau_s": float(taus[idx]), "allan_dev_m": float(adevs[idx])})
    return out


def _diagnostics_for_series(values: np.ndarray, dt_s: float, max_lag: int, nperseg: int) -> dict:
    fs_hz = 1.0 / dt_s
    acf = autocorrelation(values, max_lag=max_lag)
    freqs, psd = welch_psd(values, fs_hz=fs_hz, nperseg=nperseg)
    taus, adevs = allan_deviation(values, dt_s=dt_s)
    overall_slope = fit_allan_slope(taus, adevs, lo_s=max(2.0 * dt_s, 0.2), hi_s=min(float(np.max(taus)) if len(taus) else 1.0, 10.0))
    overall_class: SlopeClass = interpret_allan_slope(overall_slope) if math.isfinite(overall_slope) else "flicker-or-floor-like"
    return {
        "lag1_autocorrelation": float(acf[1]) if len(acf) > 1 else math.nan,
        "decorrelation_time_s": decorrelation_time(acf, dt_s),
        "psd_power_below": psd_power_fractions(freqs, psd, [0.25, 0.50, 1.00]),
        "dominant_peaks_hz": dominant_psd_peaks(freqs, psd),
        "allan_selected": selected_allan_points(taus, adevs, [dt_s, 0.25, 0.50, 1.00, 2.00, 5.00, 10.00]),
        "allan_slopes": allan_slopes_by_octave(taus, adevs),
        "overall_allan_slope": overall_slope,
        "overall_allan_class": overall_class,
    }


def analyze_axis(
    axis: str,
    t_uniform: np.ndarray,
    values_uniform: np.ndarray,
    dt_s: float,
    max_lag: int = 50,
    nperseg: int = 256,
) -> AxisNoiseSummary:
    """Analyze one uniformly sampled position axis.

    Raw diagnostics are baseline-comparable. Detrended diagnostics are reported
    separately and must not be mixed with earlier raw baseline numbers.
    """
    slope_mps, _intercept = linear_trend(t_uniform, values_uniform)
    detrended = detrend_linear(t_uniform, values_uniform)

    raw = _diagnostics_for_series(values_uniform, dt_s, max_lag, nperseg)
    det = _diagnostics_for_series(detrended, dt_s, max_lag, nperseg)

    return AxisNoiseSummary(
        axis=axis,
        sample_count=int(len(values_uniform)),
        dt_s=float(dt_s),
        sample_rate_hz=float(1.0 / dt_s),
        mean_m=float(np.mean(values_uniform)),
        std_m=float(np.std(values_uniform, ddof=1)),
        detrended_std_m=float(np.std(detrended, ddof=1)),
        linear_trend_slope_mps=float(slope_mps),
        detrending_applied=True,
        raw_lag1_autocorrelation=raw["lag1_autocorrelation"],
        raw_decorrelation_time_s=raw["decorrelation_time_s"],
        raw_psd_power_below=raw["psd_power_below"],
        raw_dominant_peaks_hz=raw["dominant_peaks_hz"],
        raw_allan_selected=raw["allan_selected"],
        raw_allan_slopes=raw["allan_slopes"],
        raw_overall_allan_slope=raw["overall_allan_slope"],
        raw_overall_allan_class=raw["overall_allan_class"],
        detrended_lag1_autocorrelation=det["lag1_autocorrelation"],
        detrended_decorrelation_time_s=det["decorrelation_time_s"],
        detrended_psd_power_below=det["psd_power_below"],
        detrended_dominant_peaks_hz=det["dominant_peaks_hz"],
        detrended_allan_selected=det["allan_selected"],
        detrended_allan_slopes=det["allan_slopes"],
        detrended_overall_allan_slope=det["overall_allan_slope"],
        detrended_overall_allan_class=det["overall_allan_class"],
        lag1_autocorrelation=raw["lag1_autocorrelation"],
        decorrelation_time_s=raw["decorrelation_time_s"],
        psd_power_below=raw["psd_power_below"],
        dominant_peaks_hz=raw["dominant_peaks_hz"],
        allan_selected=raw["allan_selected"],
        allan_slopes=raw["allan_slopes"],
        overall_allan_slope=raw["overall_allan_slope"],
        overall_allan_class=raw["overall_allan_class"],
    )


def analyze_pose_csv(path: str | Path, max_lag: int = 50, nperseg: int = 256) -> NoiseAnalysisReport:
    """Analyze a Pi-validation-compatible ``t,x,y,z`` stationary pose CSV."""
    t, x, y, _z = load_pose_csv(path)
    t_uniform, x_uniform, dt_s = uniform_resample(t, x)
    _t_uniform_y, y_uniform, _dt_y = uniform_resample(t, y, dt_s=dt_s)

    axes = {
        "x": analyze_axis("x", t_uniform, x_uniform, dt_s, max_lag=max_lag, nperseg=nperseg),
        "y": analyze_axis("y", t_uniform, y_uniform, dt_s, max_lag=max_lag, nperseg=nperseg),
    }

    return NoiseAnalysisReport(
        source=str(path),
        csv_schema=CSV_SCHEMA,
        noise_assumption_status=NOISE_ASSUMPTION_STATUS,
        white_noise_assumption_flag=WHITE_NOISE_ASSUMPTION_FLAG,
        hardware_status=HARDWARE_STATUS,
        detrending_status=DETRENDING_STATUS,
        detrending_applied=True,
        comparison_guidance=(
            "Use raw_* fields and legacy aliases for comparison to previous raw baselines "
            "such as sigma_x=0.0355 m and lag-1 rho_x=0.995. Use detrended_* fields only "
            "as drift-removed diagnostics; do not mix raw and detrended conclusions."
        ),
        sample_count_raw=int(len(t)),
        sample_count_uniform=int(len(t_uniform)),
        dt_s=float(dt_s),
        sample_rate_hz=float(1.0 / dt_s),
        axes=axes,
    )


def report_to_dict(report: NoiseAnalysisReport) -> dict:
    """Convert dataclass report to a JSON-serializable dict."""
    return asdict(report)


def _append_diag_block(lines: list[str], title: str, diag_prefix: str, axis: AxisNoiseSummary) -> None:
    get = lambda name: getattr(axis, f"{diag_prefix}_{name}")
    lines.extend(
        [
            f"- {title} lag-1 autocorrelation: `{get('lag1_autocorrelation'):.6f}`",
            f"- {title} decorrelation time: `{_fmt_optional(get('decorrelation_time_s'))} s`",
            f"- {title} overall Allan slope: `{get('overall_allan_slope'):.3f}` (`{get('overall_allan_class')}`)",
            f"- {title} PSD power fractions:",
        ]
    )
    for cutoff, frac in get("psd_power_below").items():
        lines.append(f"  - below {cutoff} Hz: `{100.0 * frac:.2f}%`")

    lines.append(f"- {title} dominant PSD peaks:")
    for peak in get("dominant_peaks_hz")[:5]:
        lines.append(f"  - `{peak['frequency_hz']:.4f} Hz`, relative power `{peak['relative_power']:.4f}`")

    lines.append(f"- {title} Allan deviation octave slopes:")
    for slope in get("allan_slopes")[:8]:
        lines.append(
            "  - "
            f"`{float(slope['tau_start_s']):.3f}-{float(slope['tau_end_s']):.3f} s`: "
            f"slope `{float(slope['slope']):.3f}` "
            f"({slope['interpretation']})"
        )


def format_markdown_report(report: NoiseAnalysisReport) -> str:
    """Return a ready-to-paste Markdown summary block."""
    lines = [
        "## Stationary AprilTag Noise Characterization",
        "",
        f"Source: `{report.source}`",
        f"CSV schema: `{','.join(report.csv_schema)}`",
        f"Noise assumption status: `{report.noise_assumption_status}`",
        f"White-noise assumption flag: `{report.white_noise_assumption_flag}`",
        f"Hardware/calibration status: `{report.hardware_status}`",
        f"Detrending status: `{report.detrending_status}`",
        f"Detrending applied: `{report.detrending_applied}`",
        f"Samples: raw `{report.sample_count_raw}`, uniform `{report.sample_count_uniform}`",
        f"Median-resampled dt: `{report.dt_s:.6f} s`",
        f"Sample rate: `{report.sample_rate_hz:.3f} Hz`",
        "",
        "> Diagnostic caveat: this report does not assume white Gaussian noise. "
        "Raw diagnostics are baseline-comparable. Detrended diagnostics are reported separately "
        "as a drift-removed view and must not be mixed with earlier raw baseline values.",
        "",
        f"> Comparison guidance: {report.comparison_guidance}",
        "",
    ]

    for axis_name in ("x", "y"):
        axis = report.axes[axis_name]
        lines.extend(
            [
                f"### {axis_name.upper()} axis",
                "",
                f"- Mean: `{axis.mean_m:.6f} m`",
                f"- Standard deviation: `{axis.std_m:.6f} m`",
                f"- Detrended standard deviation: `{axis.detrended_std_m:.6f} m`",
                f"- Linear trend slope: `{axis.linear_trend_slope_mps:.9f} m/s`",
                "",
                "#### Raw diagnostics (baseline-comparable)",
            ]
        )
        _append_diag_block(lines, "Raw", "raw", axis)
        lines.extend(["", "#### Detrended diagnostics (drift-removed)"])
        _append_diag_block(lines, "Detrended", "detrended", axis)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_text_report(report: NoiseAnalysisReport) -> str:
    """Return a compact terminal-readable report."""
    lines = [
        f"file: {report.source}",
        f"csv schema: {','.join(report.csv_schema)}",
        f"noise assumption status: {report.noise_assumption_status}",
        f"white noise assumption flag: {report.white_noise_assumption_flag}",
        f"hardware status: {report.hardware_status}",
        f"detrending status: {report.detrending_status}",
        f"comparison guidance: {report.comparison_guidance}",
        f"samples raw/uniform: {report.sample_count_raw}/{report.sample_count_uniform}",
        f"dt: {report.dt_s:.6f} s",
        f"sample rate: {report.sample_rate_hz:.3f} Hz",
    ]
    for axis_name in ("x", "y"):
        axis = report.axes[axis_name]
        lines.extend(
            [
                "",
                f"========== {axis_name} ==========" ,
                f"mean: {axis.mean_m:.6f} m",
                f"std: {axis.std_m:.6f} m",
                f"detrended std: {axis.detrended_std_m:.6f} m",
                f"linear trend slope: {axis.linear_trend_slope_mps:.9f} m/s",
                f"raw lag-1 acf: {axis.raw_lag1_autocorrelation:.6f}",
                f"detrended lag-1 acf: {axis.detrended_lag1_autocorrelation:.6f}",
                f"raw Allan slope: {axis.raw_overall_allan_slope:.3f} {axis.raw_overall_allan_class}",
                f"detrended Allan slope: {axis.detrended_overall_allan_slope:.3f} {axis.detrended_overall_allan_class}",
                "raw PSD power fractions:",
            ]
        )
        for cutoff, frac in axis.raw_psd_power_below.items():
            lines.append(f"  below {cutoff} Hz: {100.0 * frac:.2f}%")
        lines.append("detrended PSD power fractions:")
        for cutoff, frac in axis.detrended_psd_power_below.items():
            lines.append(f"  below {cutoff} Hz: {100.0 * frac:.2f}%")
    return "\n".join(lines)


def generate_white_noise(count: int, std_m: float = 0.004, seed: int = 1) -> np.ndarray:
    """Generate synthetic position white noise."""
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, std_m, count)


def generate_random_walk_noise(count: int, step_std_m: float = 0.001, seed: int = 2) -> np.ndarray:
    """Generate synthetic position random-walk noise."""
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(0.0, step_std_m, count))


def generate_flicker_like_noise(count: int, amplitude_m: float = 0.001, seed: int = 3) -> np.ndarray:
    """Generate approximate 1/f, flicker-like position noise with flat Allan slope.

    This is a frequency-domain synthetic source used only for unit testing the
    classifier boundary. It is not a hardware replay.
    """
    rng = np.random.default_rng(seed)
    freqs = np.fft.rfftfreq(count, d=1.0)
    scale = np.zeros_like(freqs)
    scale[1:] = 1.0 / np.sqrt(freqs[1:])
    spectrum = (rng.normal(size=len(freqs)) + 1j * rng.normal(size=len(freqs))) * scale
    spectrum[0] = 0.0
    x = np.fft.irfft(spectrum, n=count)
    x = x / max(float(np.std(x)), 1e-12) * amplitude_m
    return x


def generate_ar1_drift_noise(
    count: int,
    rho: float = 0.985,
    process_std_m: float = 0.0012,
    white_std_m: float = 0.0025,
    seed: int = 4,
) -> np.ndarray:
    """Generate synthetic AR(1) drift matching the PR #18 software-regime pattern.

    This mirrors ``stationary_colored_noise_hide_reveal`` in
    ``ghost_software_regime.py`` and remains synthetic, not hardware Allan/PSD
    replay.
    """
    rng = np.random.default_rng(seed)
    drift = np.zeros(count, dtype=float)
    for k in range(1, count):
        drift[k] = rho * drift[k - 1] + rng.normal(0.0, process_std_m)
    return drift + rng.normal(0.0, white_std_m, count)


def _fmt_optional(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.6f}"


def write_reports(report: NoiseAnalysisReport, json_out: Path | None = None, markdown_out: Path | None = None) -> None:
    """Write JSON and/or Markdown reports."""
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report_to_dict(report), indent=2) + "\n")
    if markdown_out is not None:
        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text(format_markdown_report(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze stationary AprilTag pose noise from t,x,y,z CSV logs.")
    parser.add_argument("csv_path", help="Input CSV with columns t,x,y,z; extra columns are ignored")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown report block to stdout.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional machine-readable JSON output path.")
    parser.add_argument("--markdown-out", type=Path, default=None, help="Optional Markdown report output path.")
    parser.add_argument("--max-lag", type=int, default=50, help="Maximum autocorrelation lag in samples.")
    parser.add_argument("--nperseg", type=int, default=256, help="Welch PSD segment length.")
    parser.add_argument("--out", type=Path, default=None, help="Legacy output path for the selected stdout format.")
    args = parser.parse_args(argv)

    report = analyze_pose_csv(args.csv_path, max_lag=args.max_lag, nperseg=args.nperseg)
    write_reports(report, json_out=args.json_out, markdown_out=args.markdown_out)

    if args.json:
        output = json.dumps(report_to_dict(report), indent=2)
    elif args.markdown:
        output = format_markdown_report(report)
    else:
        output = format_text_report(report)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output if output.endswith("\n") else output + "\n")
    elif args.json_out is None and args.markdown_out is None:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
