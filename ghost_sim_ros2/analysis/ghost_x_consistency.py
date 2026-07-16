"""Formal consistency diagnostics for GHOST-X canonical estimator replays.

The module intentionally distinguishes exact Gaussian NIS, moment-matched
mixture diagnostics, and cases where a scalar NIS claim is invalid.  Position
NEES is computed only when deterministic software truth and a finite positive
definite 2x2 position covariance are available.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.stats import chi2, jarque_bera


STATE_DIM = 4
MEAS_DIM = 2
H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)


@dataclass(frozen=True)
class QuadraticSummary:
    name: str
    dof: int
    count: int
    mean: float | None
    median: float | None
    individual_bounds_95: tuple[float, float]
    mean_bounds_95: tuple[float, float] | None
    individual_inside_fraction: float | None
    mean_inside_95: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dof": self.dof,
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "individual_bounds_95": {"low": self.individual_bounds_95[0], "high": self.individual_bounds_95[1]},
            "mean_bounds_95": None
            if self.mean_bounds_95 is None
            else {"low": self.mean_bounds_95[0], "high": self.mean_bounds_95[1]},
            "individual_inside_fraction": self.individual_inside_fraction,
            "mean_inside_95": self.mean_inside_95,
        }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
            rows.append(value)
    return rows


def cv_transition(dt_s: float) -> np.ndarray:
    dt = _positive(dt_s, "dt_s")
    return np.array(
        [[1.0, 0.0, dt, 0.0], [0.0, 1.0, 0.0, dt], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=float,
    )


def white_acceleration_q(dt_s: float, acceleration_std_mps2: float) -> np.ndarray:
    dt = _positive(dt_s, "dt_s")
    sigma = _positive(acceleration_std_mps2, "acceleration_std_mps2")
    return sigma * sigma * np.array(
        [
            [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
            [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
            [dt**3 / 2.0, 0.0, dt**2, 0.0],
            [0.0, dt**3 / 2.0, 0.0, dt**2],
        ],
        dtype=float,
    )


def quadratic_form(error: Iterable[float], covariance: Iterable[Iterable[float]]) -> float | None:
    vector = np.asarray(list(error), dtype=float).reshape(-1, 1)
    matrix = np.asarray(list(list(row) for row in covariance), dtype=float)
    if matrix.shape != (vector.shape[0], vector.shape[0]) or not np.isfinite(vector).all() or not np.isfinite(matrix).all():
        return None
    matrix = 0.5 * (matrix + matrix.T)
    try:
        factor = np.linalg.cholesky(matrix)
        whitened = np.linalg.solve(factor, vector)
    except np.linalg.LinAlgError:
        return None
    value = float((whitened.T @ whitened)[0, 0])
    return value if math.isfinite(value) and value >= 0.0 else None


def summarize_quadratic(name: str, values: Iterable[float], dof: int) -> QuadraticSummary:
    clean = [float(v) for v in values if math.isfinite(float(v)) and float(v) >= 0.0]
    individual = (float(chi2.ppf(0.025, dof)), float(chi2.ppf(0.975, dof)))
    if not clean:
        return QuadraticSummary(name, dof, 0, None, None, individual, None, None, None)
    n = len(clean)
    mean_bounds = (float(chi2.ppf(0.025, dof * n) / n), float(chi2.ppf(0.975, dof * n) / n))
    mean_value = float(statistics.fmean(clean))
    inside = sum(individual[0] <= value <= individual[1] for value in clean) / n
    return QuadraticSummary(
        name=name,
        dof=dof,
        count=n,
        mean=mean_value,
        median=float(statistics.median(clean)),
        individual_bounds_95=individual,
        mean_bounds_95=mean_bounds,
        individual_inside_fraction=float(inside),
        mean_inside_95=bool(mean_bounds[0] <= mean_value <= mean_bounds[1]),
    )


def residual_diagnostics(residuals: list[list[float]], max_lag: int = 20) -> dict[str, Any]:
    if len(residuals) < 8:
        return {"valid": False, "reason": "FEWER_THAN_8_RESIDUALS"}
    array = np.asarray(residuals, dtype=float)
    dimensions = []
    for index, axis in enumerate(("x", "y")):
        values = array[:, index]
        jb = jarque_bera(values)
        q_stat, q_p = ljung_box(values, min(max_lag, max(1, len(values) // 5)))
        dimensions.append(
            {
                "axis": axis,
                "count": int(len(values)),
                "mean": float(np.mean(values)),
                "std": float(np.std(values, ddof=1)),
                "jarque_bera_statistic": float(jb.statistic),
                "jarque_bera_p_value": float(jb.pvalue),
                "gaussian_at_alpha_0_05": bool(jb.pvalue >= 0.05),
                "ljung_box_lags": int(min(max_lag, max(1, len(values) // 5))),
                "ljung_box_statistic": float(q_stat),
                "ljung_box_p_value": float(q_p),
                "white_at_alpha_0_05": bool(q_p >= 0.05),
            }
        )
    return {"valid": True, "dimensions": dimensions}


def ljung_box(values: np.ndarray, lags: int) -> tuple[float, float]:
    centered = np.asarray(values, dtype=float) - float(np.mean(values))
    n = len(centered)
    denominator = float(centered @ centered)
    if n < 3 or denominator <= 0.0:
        return 0.0, 1.0
    correlations = []
    for lag in range(1, lags + 1):
        correlations.append(float(centered[lag:] @ centered[:-lag] / denominator))
    statistic = float(n * (n + 2.0) * sum(rho * rho / (n - lag) for lag, rho in enumerate(correlations, start=1)))
    return statistic, float(chi2.sf(statistic, lags))


def run_cv_consistency(
    stream_rows: list[dict[str, Any]],
    measurement_covariance_xy: np.ndarray,
    *,
    acceleration_std_mps2: float = 0.65,
) -> dict[str, Any]:
    r = np.asarray(measurement_covariance_xy, dtype=float)
    x: np.ndarray | None = None
    p: np.ndarray | None = None
    nis_values: list[float] = []
    nees_values: list[float] = []
    residuals: list[list[float]] = []
    samples: list[dict[str, Any]] = []
    for row in stream_rows:
        dt = float(row["dt_s"])
        measurement = row.get("measurement_xy_m") if bool(row.get("visible")) else None
        truth = row["truth"]
        truth_position = np.array([truth["x_m"], truth["y_m"]], dtype=float)
        if x is None:
            if measurement is None:
                continue
            z = np.asarray(measurement, dtype=float)
            x = np.array([z[0], z[1], 0.0, 0.0], dtype=float)
            p = np.diag([0.04, 0.04, 0.8, 0.8])
        else:
            assert p is not None
            f = cv_transition(dt)
            x = f @ x
            p = 0.5 * (f @ p @ f.T + white_acceleration_q(dt, acceleration_std_mps2) + (f @ p @ f.T + white_acceleration_q(dt, acceleration_std_mps2)).T)
            if measurement is not None:
                z = np.asarray(measurement, dtype=float)
                innovation = z - H @ x
                s = 0.5 * (H @ p @ H.T + r + (H @ p @ H.T + r).T)
                nis = quadratic_form(innovation, s)
                if nis is not None:
                    nis_values.append(nis)
                    residuals.append([float(innovation[0]), float(innovation[1])])
                gain = np.linalg.solve(s.T, (p @ H.T).T).T
                x = x + gain @ innovation
                joseph = np.eye(STATE_DIM) - gain @ H
                p = 0.5 * (joseph @ p @ joseph.T + gain @ r @ gain.T + (joseph @ p @ joseph.T + gain @ r @ gain.T).T)
        assert x is not None and p is not None
        position_error = x[:2] - truth_position
        nees = quadratic_form(position_error, p[:2, :2])
        if nees is not None:
            nees_values.append(nees)
        samples.append(
            {
                "t_s": float(row["t_s"]),
                "visible": bool(row.get("visible")),
                "position_nees": nees,
                "nis": nis_values[-1] if measurement is not None and nis_values else None,
            }
        )
    return {
        "nis_validity": "FORMAL_LINEAR_GAUSSIAN_NIS_IF_WHITE_GAUSSIAN_MODEL_ASSUMPTIONS_HOLD",
        "nees_validity": "SYNTHETIC_TRUTH_POSITION_NEES_ONLY",
        "nis": summarize_quadratic("NIS", nis_values, MEAS_DIM).to_dict(),
        "position_nees": summarize_quadratic("POSITION_NEES", nees_values, 2).to_dict(),
        "innovation_residuals": residual_diagnostics(residuals),
        "samples": samples,
    }


def output_position_nees(stream_rows: list[dict[str, Any]], output_rows: list[dict[str, Any]]) -> list[float]:
    by_sequence = {int(row["sequence"]): row for row in output_rows}
    values: list[float] = []
    for stream in stream_rows:
        output = by_sequence.get(int(stream["sequence"]))
        if not output or not output.get("initialized") or not isinstance(output.get("state"), dict):
            continue
        covariance = np.asarray(output.get("covariance"), dtype=float)
        if covariance.shape != (4, 4):
            continue
        truth = stream["truth"]
        error = [float(output["state"]["x_m"]) - float(truth["x_m"]), float(output["state"]["y_m"]) - float(truth["y_m"])]
        value = quadratic_form(error, covariance[:2, :2])
        if value is not None:
            values.append(value)
    return values


def approximate_forecast_nis(
    stream_rows: list[dict[str, Any]],
    output_rows: list[dict[str, Any]],
    measurement_covariance_xy: np.ndarray,
    *,
    q_smooth: float,
    q_maneuver: float,
) -> tuple[list[float], list[list[float]]]:
    by_sequence = {int(row["sequence"]): row for row in output_rows}
    values: list[float] = []
    residuals: list[list[float]] = []
    previous: dict[str, Any] | None = None
    r = np.asarray(measurement_covariance_xy, dtype=float)
    for stream in stream_rows:
        current = by_sequence.get(int(stream["sequence"]))
        if previous is not None and bool(stream.get("visible")) and isinstance(stream.get("measurement_xy_m"), list):
            state = previous.get("state")
            covariance = np.asarray(previous.get("covariance"), dtype=float)
            if isinstance(state, dict) and covariance.shape == (4, 4):
                dt = float(stream["dt_s"])
                f = cv_transition(dt)
                vector = np.array([state["x_m"], state["y_m"], state["vx_mps"], state["vy_mps"]], dtype=float)
                probabilities = previous.get("mode_probabilities") or {}
                smooth_probability = float(probabilities.get("smooth_cv", 0.5))
                maneuver_probability = float(probabilities.get("maneuver_cv", 1.0 - smooth_probability))
                q = smooth_probability * white_acceleration_q(dt, q_smooth) + maneuver_probability * white_acceleration_q(dt, q_maneuver)
                predicted_state = f @ vector
                predicted_covariance = 0.5 * (f @ covariance @ f.T + q + (f @ covariance @ f.T + q).T)
                measurement = np.asarray(stream["measurement_xy_m"], dtype=float)
                innovation = measurement - H @ predicted_state
                s = 0.5 * (H @ predicted_covariance @ H.T + r + (H @ predicted_covariance @ H.T + r).T)
                value = quadratic_form(innovation, s)
                if value is not None:
                    values.append(value)
                    residuals.append([float(innovation[0]), float(innovation[1])])
        if current and current.get("initialized"):
            previous = current
    return values, residuals


def analyze_campaign(campaign_dir: Path) -> dict[str, Any]:
    campaign_dir = campaign_dir.resolve()
    streams = sorted((campaign_dir / "canonical_streams").glob("*.jsonl"))
    if not streams:
        raise ValueError("no canonical streams found")
    trial_reports: list[dict[str, Any]] = []
    pooled: dict[str, list[float]] = {"cv_nis": [], "cv_nees": [], "imm_nis": [], "imm_nees": [], "mh_nees": []}
    residual_pool: dict[str, list[list[float]]] = {"cv": [], "imm": []}

    for stream_path in streams:
        trial_id = stream_path.stem
        stream_rows = load_jsonl(stream_path)
        r = np.asarray(stream_rows[0]["measurement_covariance_xy_m2"], dtype=float)
        cv_report = run_cv_consistency(stream_rows, r)
        cv_nis = [sample["nis"] for sample in cv_report["samples"] if sample.get("nis") is not None]
        cv_nees = [sample["position_nees"] for sample in cv_report["samples"] if sample.get("position_nees") is not None]
        pooled["cv_nis"].extend(cv_nis)
        pooled["cv_nees"].extend(cv_nees)

        outputs: dict[str, list[dict[str, Any]]] = {}
        for estimator in ("formal_imm", "ghost_mh"):
            output_path = campaign_dir / "estimator_outputs" / f"{trial_id}__{estimator}.jsonl"
            outputs[estimator] = load_jsonl(output_path)
        imm_nees = output_position_nees(stream_rows, outputs["formal_imm"])
        mh_nees = output_position_nees(stream_rows, outputs["ghost_mh"])
        imm_nis, imm_residuals = approximate_forecast_nis(
            stream_rows,
            outputs["formal_imm"],
            r,
            q_smooth=0.015,
            q_maneuver=0.75,
        )
        pooled["imm_nis"].extend(imm_nis)
        pooled["imm_nees"].extend(imm_nees)
        pooled["mh_nees"].extend(mh_nees)
        # Reconstruct residual vectors from diagnostics only for pooled reporting.
        cv_dims = cv_report["innovation_residuals"]
        residual_pool["imm"].extend(imm_residuals)
        trial_reports.append(
            {
                "trial_id": trial_id,
                "scenario_family": stream_rows[0]["scenario_family"],
                "cv": {
                    "nis": summarize_quadratic("NIS", cv_nis, 2).to_dict(),
                    "position_nees": summarize_quadratic("POSITION_NEES", cv_nees, 2).to_dict(),
                    "residual_diagnostics": cv_dims,
                },
                "formal_imm": {
                    "nis": summarize_quadratic("MOMENT_MATCHED_NIS", imm_nis, 2).to_dict(),
                    "position_nees": summarize_quadratic("POSITION_NEES", imm_nees, 2).to_dict(),
                    "residual_diagnostics": residual_diagnostics(imm_residuals),
                },
                "ghost_mh": {
                    "nis": {
                        "valid": False,
                        "reason": "MULTIMODAL_NON_GAUSSIAN_BELIEF_NO_SINGLE_FORMAL_NIS",
                    },
                    "position_nees": summarize_quadratic("MOMENT_MATCHED_POSITION_NEES", mh_nees, 2).to_dict(),
                },
            }
        )

    covariance_sensitivity: list[dict[str, Any]] = []
    for scale in (0.5, 1.0, 2.0):
        nis_values: list[float] = []
        nees_values: list[float] = []
        for stream_path in streams:
            rows = load_jsonl(stream_path)
            nominal_r = np.asarray(rows[0]["measurement_covariance_xy_m2"], dtype=float)
            report = run_cv_consistency(rows, nominal_r * scale)
            nis_values.extend(sample["nis"] for sample in report["samples"] if sample.get("nis") is not None)
            nees_values.extend(sample["position_nees"] for sample in report["samples"] if sample.get("position_nees") is not None)
        covariance_sensitivity.append(
            {
                "measurement_covariance_scale": scale,
                "cv_nis": summarize_quadratic("NIS", nis_values, 2).to_dict(),
                "cv_position_nees": summarize_quadratic("POSITION_NEES", nees_values, 2).to_dict(),
                "selection_status": "SENSITIVITY_ONLY_NOT_A_PHYSICAL_MODEL_SELECTION",
            }
        )

    return {
        "schema_version": 1,
        "phase": "G6_FORMAL_CONSISTENCY",
        "canonical_trials": len(streams),
        "truth_validity": "DETERMINISTIC_ANALYTIC_SOFTWARE_TRUTH_WITH_DECLARED_NEGLIGIBLE_NUMERICAL_COVARIANCE",
        "pooled": {
            "cv": {
                "nis": summarize_quadratic("NIS", pooled["cv_nis"], 2).to_dict(),
                "position_nees": summarize_quadratic("POSITION_NEES", pooled["cv_nees"], 2).to_dict(),
                "nis_validity": "FORMAL_ONLY_IF_LINEAR_WHITE_GAUSSIAN_ASSUMPTIONS_HOLD",
            },
            "formal_imm": {
                "nis": summarize_quadratic("MOMENT_MATCHED_MIXTURE_NIS", pooled["imm_nis"], 2).to_dict(),
                "position_nees": summarize_quadratic("POSITION_NEES", pooled["imm_nees"], 2).to_dict(),
                "nis_validity": "APPROXIMATE_MOMENT_MATCHED_GAUSSIAN_DIAGNOSTIC_NOT_EXACT_MIXTURE_NIS",
            },
            "ghost_mh": {
                "nis": {"valid": False, "reason": "MULTIMODAL_NON_GAUSSIAN_BELIEF"},
                "position_nees": summarize_quadratic("MOMENT_MATCHED_POSITION_NEES", pooled["mh_nees"], 2).to_dict(),
                "nees_validity": "SYNTHETIC_MOMENT_MATCHED_DIAGNOSTIC_ONLY",
            },
        },
        "covariance_sensitivity": covariance_sensitivity,
        "trials": trial_reports,
        "limitations": [
            "Hardware NEES remains invalid until controlled physical truth and truth uncertainty are available.",
            "IMM NIS is a moment-matched approximation because the predictive distribution is a Gaussian mixture.",
            "A single formal NIS is not reported for GHOST-MH during multimodal intervals.",
            "Colored or non-Gaussian residuals invalidate textbook chi-square interpretation.",
        ],
    }


def write_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "GHOST_X_G6_CONSISTENCY.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out_dir / "GHOST_X_G6_CONSISTENCY.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["estimator", "metric", "count", "mean", "mean_low_95", "mean_high_95", "mean_inside_95"])
        for estimator, values in report["pooled"].items():
            for metric in ("nis", "position_nees"):
                summary = values.get(metric)
                if not isinstance(summary, dict) or "count" not in summary:
                    continue
                bounds = summary.get("mean_bounds_95") or {}
                writer.writerow(
                    [estimator, metric, summary.get("count"), summary.get("mean"), bounds.get("low"), bounds.get("high"), summary.get("mean_inside_95")]
                )
    lines = [
        "# GHOST-X G6 Consistency Report",
        "",
        f"Canonical trials: `{report['canonical_trials']}`",
        "",
        "| Estimator | Metric | Samples | Mean | 95% mean interval | Inside? |",
        "|---|---|---:|---:|---|---|",
    ]
    for estimator, values in report["pooled"].items():
        for metric in ("nis", "position_nees"):
            summary = values.get(metric)
            if not isinstance(summary, dict) or "count" not in summary:
                continue
            bounds = summary.get("mean_bounds_95")
            interval = "NA" if not bounds else f"[{bounds['low']:.4g}, {bounds['high']:.4g}]"
            mean = summary.get("mean")
            mean_text = "NA" if mean is None else f"{mean:.4g}"
            lines.append(f"| `{estimator}` | `{metric}` | {summary['count']} | {mean_text} | {interval} | {summary.get('mean_inside_95')} |")
    lines.extend(
        [
            "",
            "## Validity boundaries",
            "",
            "- CV NIS has textbook meaning only under the declared linear, white, Gaussian assumptions.",
            "- IMM NIS is a moment-matched mixture diagnostic, not an exact mixture-distribution test.",
            "- GHOST-MH has no single formal NIS during multi-modal intervals.",
            "- Position NEES here is valid only against deterministic synthetic truth; physical NEES remains pending.",
            "",
        ]
    )
    (out_dir / "GHOST_X_G6_CONSISTENCY.md").write_text("\n".join(lines), encoding="utf-8")


def _positive(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return result
