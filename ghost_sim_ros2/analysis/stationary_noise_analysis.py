"""Stationary AprilTag pose noise characterization utilities.

This module is intentionally hardware-independent. It analyzes CSV logs with
columns ``t,x,y,z`` and reports autocorrelation, Welch PSD, and Allan deviation
after resampling onto a uniform time grid.

Important estimator caveat:
These diagnostics do not assume the pose noise is white. If later code chooses
to use white-Gaussian measurement covariance, that assumption must be stated
separately and validated against these colored-noise diagnostics.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class AxisNoiseSummary:
    axis: str
    sample_count: int
    dt_s: float
    sample_rate_hz: float
    mean_m: float
    std_m: float
    detrended_std_m: float
    lag1_autocorrelation: float
    decorrelation_time_s: float | None
    psd_power_below: dict[str, float]
    dominant_peaks_hz: list[dict[str, float]]
    allan_selected: list[dict[str, float]]
    allan_slopes: list[dict[str, float | str]]


@dataclass(frozen=True)
class NoiseAnalysisReport:
    source: str
    sample_count_raw: int
    sample_count_uniform: int
    dt_s: float
    sample_rate_hz: float
    axes: dict[str, AxisNoiseSummary]


def load_pose_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load a stationary pose CSV with columns t,x,y,z."""
    rows: list[tuple[float, float, float, float]] = []
    with Path(path).expanduser().open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"t", "x", "y", "z"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"CSV must contain columns {sorted(required)}; got {reader.fieldnames}")
        for row in reader:
            rows.append((float(row["t"]), float(row["x"]), float(row["y"]), float(row["z"])))

    if len(rows) < 4:
        raise ValueError("Need at least four pose samples for noise analysis.")

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


def detrend_linear(t: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Remove the best-fit line from a time series."""
    if len(values) < 2:
        return values - np.mean(values)
    coeff = np.polyfit(t, values, 1)
    return values - np.polyval(coeff, t)


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
    """Compute a simple Welch PSD estimate using only NumPy."""
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
    """Return dominant local PSD peaks. Falls back to largest bins if needed."""
    total = float(np.sum(psd))
    if total <= 0.0:
        return []

    local_maxima: list[int] = []
    for i in range(1, len(psd) - 1):
        if freqs[i] > 0.0 and psd[i] >= psd[i - 1] and psd[i] >= psd[i + 1]:
            local_maxima.append(i)

    candidates = local_maxima if local_maxima else [i for i in range(1, len(psd)) if freqs[i] > 0.0]
    candidates = sorted(candidates, key=lambda i: float(psd[i]), reverse=True)[:count]
    return [
        {"frequency_hz": float(freqs[i]), "relative_power": float(psd[i] / total)}
        for i in candidates
    ]


def allan_deviation(values: np.ndarray, dt_s: float, points: int = 48) -> tuple[np.ndarray, np.ndarray]:
    """Overlapping Allan deviation for position-like data.

    For position white noise, slope is near -1/2.
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


def interpret_allan_slope(slope: float) -> str:
    """Interpret Allan deviation slope."""
    if slope < -0.30:
        return "white-noise-like"
    if slope <= 0.30:
        return "flicker-or-floor-like"
    return "random-walk-or-drift-like"


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


def analyze_axis(
    axis: str,
    t_uniform: np.ndarray,
    values_uniform: np.ndarray,
    dt_s: float,
    max_lag: int = 50,
    nperseg: int = 256,
) -> AxisNoiseSummary:
    """Analyze one uniformly sampled position axis."""
    fs_hz = 1.0 / dt_s
    detrended = detrend_linear(t_uniform, values_uniform)

    acf = autocorrelation(detrended, max_lag=max_lag)
    freqs, psd = welch_psd(detrended, fs_hz=fs_hz, nperseg=nperseg)
    taus, adevs = allan_deviation(detrended, dt_s=dt_s)

    return AxisNoiseSummary(
        axis=axis,
        sample_count=int(len(values_uniform)),
        dt_s=float(dt_s),
        sample_rate_hz=float(fs_hz),
        mean_m=float(np.mean(values_uniform)),
        std_m=float(np.std(values_uniform, ddof=1)),
        detrended_std_m=float(np.std(detrended, ddof=1)),
        lag1_autocorrelation=float(acf[1]) if len(acf) > 1 else math.nan,
        decorrelation_time_s=decorrelation_time(acf, dt_s),
        psd_power_below=psd_power_fractions(freqs, psd, [0.25, 0.50, 1.00]),
        dominant_peaks_hz=dominant_psd_peaks(freqs, psd),
        allan_selected=selected_allan_points(taus, adevs, [dt_s, 0.25, 0.50, 1.00, 2.00, 5.00, 10.00]),
        allan_slopes=allan_slopes_by_octave(taus, adevs),
    )


def analyze_pose_csv(path: str | Path, max_lag: int = 50, nperseg: int = 256) -> NoiseAnalysisReport:
    """Analyze x/y stationary pose noise from a CSV log."""
    t, x, y, _z = load_pose_csv(path)
    t_uniform, x_uniform, dt_s = uniform_resample(t, x)
    _t_uniform_y, y_uniform, _dt_y = uniform_resample(t, y, dt_s=dt_s)

    axes = {
        "x": analyze_axis("x", t_uniform, x_uniform, dt_s, max_lag=max_lag, nperseg=nperseg),
        "y": analyze_axis("y", t_uniform, y_uniform, dt_s, max_lag=max_lag, nperseg=nperseg),
    }

    return NoiseAnalysisReport(
        source=str(path),
        sample_count_raw=int(len(t)),
        sample_count_uniform=int(len(t_uniform)),
        dt_s=float(dt_s),
        sample_rate_hz=float(1.0 / dt_s),
        axes=axes,
    )


def report_to_dict(report: NoiseAnalysisReport) -> dict:
    """Convert dataclass report to JSON-serializable dict."""
    return asdict(report)


def format_markdown_report(report: NoiseAnalysisReport) -> str:
    """Return a ready-to-paste Markdown summary block."""
    lines = [
        "## Stationary AprilTag Noise Characterization",
        "",
        f"Source: `{report.source}`",
        f"Samples: raw `{report.sample_count_raw}`, uniform `{report.sample_count_uniform}`",
        f"Median-resampled dt: `{report.dt_s:.6f} s`",
        f"Sample rate: `{report.sample_rate_hz:.3f} Hz`",
        "",
        "> Diagnostic caveat: this report does not assume white Gaussian noise. "
        "Autocorrelation, PSD, and Allan deviation are used to check whether that assumption is defensible.",
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
                f"- Lag-1 autocorrelation: `{axis.lag1_autocorrelation:.6f}`",
                f"- Decorrelation time: `{_fmt_optional(axis.decorrelation_time_s)} s`",
                "- PSD power fractions:",
            ]
        )
        for cutoff, frac in axis.psd_power_below.items():
            lines.append(f"  - below {cutoff} Hz: `{100.0 * frac:.2f}%`")

        lines.append("- Dominant PSD peaks:")
        for peak in axis.dominant_peaks_hz[:5]:
            lines.append(
                f"  - `{peak['frequency_hz']:.4f} Hz`, relative power `{peak['relative_power']:.4f}`"
            )

        lines.append("- Allan deviation octave slopes:")
        for slope in axis.allan_slopes[:8]:
            lines.append(
                "  - "
                f"`{float(slope['tau_start_s']):.3f}-{float(slope['tau_end_s']):.3f} s`: "
                f"slope `{float(slope['slope']):.3f}` "
                f"({slope['interpretation']})"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_text_report(report: NoiseAnalysisReport) -> str:
    """Return a compact terminal-readable report."""
    lines = [
        f"file: {report.source}",
        f"samples raw/uniform: {report.sample_count_raw}/{report.sample_count_uniform}",
        f"dt: {report.dt_s:.6f} s",
        f"sample rate: {report.sample_rate_hz:.3f} Hz",
    ]
    for axis_name in ("x", "y"):
        axis = report.axes[axis_name]
        lines.extend(
            [
                "",
                f"========== {axis_name} ==========",
                f"mean: {axis.mean_m:.6f} m",
                f"std: {axis.std_m:.6f} m",
                f"detrended std: {axis.detrended_std_m:.6f} m",
                f"lag-1 acf: {axis.lag1_autocorrelation:.6f}",
                f"decorrelation time: {_fmt_optional(axis.decorrelation_time_s)} s",
                "PSD power fractions:",
            ]
        )
        for cutoff, frac in axis.psd_power_below.items():
            lines.append(f"  below {cutoff} Hz: {100.0 * frac:.2f}%")
        lines.append("dominant peaks:")
        for peak in axis.dominant_peaks_hz[:5]:
            lines.append(f"  {peak['frequency_hz']:.4f} Hz rel={peak['relative_power']:.4f}")
        lines.append("Allan slopes:")
        for slope in axis.allan_slopes[:8]:
            lines.append(
                f"  {float(slope['tau_start_s']):.3f}-{float(slope['tau_end_s']):.3f}s "
                f"slope={float(slope['slope']):.3f} {slope['interpretation']}"
            )
    return "\n".join(lines)


def _fmt_optional(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.6f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze stationary AprilTag pose noise from t,x,y,z CSV logs.")
    parser.add_argument("csv_path", help="Input CSV with columns t,x,y,z")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown report block.")
    parser.add_argument("--max-lag", type=int, default=50, help="Maximum autocorrelation lag in samples.")
    parser.add_argument("--nperseg", type=int, default=256, help="Welch PSD segment length.")
    parser.add_argument("--out", type=Path, default=None, help="Optional output path for the selected report format.")
    args = parser.parse_args(argv)

    report = analyze_pose_csv(args.csv_path, max_lag=args.max_lag, nperseg=args.nperseg)

    if args.json:
        output = json.dumps(report_to_dict(report), indent=2)
    elif args.markdown:
        output = format_markdown_report(report)
    else:
        output = format_text_report(report)

    if args.out is not None:
        args.out.write_text(output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
