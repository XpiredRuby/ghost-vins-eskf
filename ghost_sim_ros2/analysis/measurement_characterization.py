"""GHOST-X G3 multi-condition stationary measurement characterization.

The analyzer keeps three concepts separate:
1. empirical short-window measurement dispersion after removing the trial mean or trend;
2. fixture-referenced bias, when declared truth and uncertainty are available;
3. calibration/fixture uncertainty, which cannot be identified from repeated camera
   measurements alone and is therefore reported separately rather than absorbed into R.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml
from scipy.stats import chi2, jarque_bera, kurtosis, skew


EPS = 1.0e-12


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_pose_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    times: list[float] = []
    positions: list[tuple[float, float]] = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"t", "x", "y"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain t,x,y columns")
        for line, row in enumerate(reader, start=2):
            try:
                t = float(row["t"])
                x = float(row["x"])
                y = float(row["y"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"non-numeric pose at {path}:{line}") from exc
            if not all(math.isfinite(v) for v in (t, x, y)):
                raise ValueError(f"nonfinite pose at {path}:{line}")
            times.append(t)
            positions.append((x, y))
    if len(times) < 8:
        raise ValueError(f"{path} contains fewer than eight samples")
    order = np.argsort(np.asarray(times, dtype=float))
    return np.asarray(times, dtype=float)[order], np.asarray(positions, dtype=float)[order]


def fixed_window(
    times: np.ndarray, positions: np.ndarray, start_s: float, end_s: float
) -> tuple[np.ndarray, np.ndarray]:
    mask = (times >= start_s) & (times < end_s)
    if int(np.sum(mask)) < 8:
        raise ValueError(f"fixed window [{start_s},{end_s}) contains fewer than eight samples")
    return times[mask], positions[mask]


def linear_detrend(times: np.ndarray, positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centered_t = times - float(np.mean(times))
    design = np.column_stack([np.ones_like(centered_t), centered_t])
    coefficients, *_ = np.linalg.lstsq(design, positions, rcond=None)
    trend = design @ coefficients
    return positions - trend, coefficients[1, :]


def centered_residuals(positions: np.ndarray) -> np.ndarray:
    return positions - np.mean(positions, axis=0, keepdims=True)


def regularize_covariance(covariance: np.ndarray, floor: float = 1.0e-12) -> np.ndarray:
    covariance = np.asarray(covariance, dtype=float)
    covariance = 0.5 * (covariance + covariance.T)
    values, vectors = np.linalg.eigh(covariance)
    values = np.maximum(values, floor)
    return vectors @ np.diag(values) @ vectors.T


def covariance_from_residuals(residuals: np.ndarray) -> np.ndarray:
    if residuals.shape[0] < 2:
        raise ValueError("at least two residual samples required")
    return regularize_covariance(np.cov(residuals.T, ddof=1))


def correlation_from_covariance(covariance: np.ndarray) -> float:
    denominator = math.sqrt(max(EPS, float(covariance[0, 0] * covariance[1, 1])))
    return float(np.clip(covariance[0, 1] / denominator, -0.999, 0.999))


def autocorrelation(values: np.ndarray, max_lag: int) -> np.ndarray:
    x = np.asarray(values, dtype=float) - float(np.mean(values))
    denominator = float(np.dot(x, x))
    if denominator <= EPS:
        result = np.zeros(max_lag + 1, dtype=float)
        result[0] = 1.0
        return result
    return np.asarray(
        [1.0] + [float(np.dot(x[:-lag], x[lag:]) / denominator) for lag in range(1, max_lag + 1)],
        dtype=float,
    )


def ljung_box(values: np.ndarray, lags: Iterable[int]) -> list[dict[str, float]]:
    n = len(values)
    max_lag = max(int(v) for v in lags)
    if n <= max_lag + 2:
        return []
    acf = autocorrelation(values, max_lag)
    results: list[dict[str, float]] = []
    for lag in lags:
        lag = int(lag)
        q = n * (n + 2.0) * sum(float(acf[k] ** 2) / (n - k) for k in range(1, lag + 1))
        results.append({"lag": lag, "q": float(q), "p_value": float(chi2.sf(q, lag))})
    return results


def axis_diagnostics(
    raw_residual: np.ndarray,
    detrended_residual: np.ndarray,
    lags: list[int],
    alpha: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, values in (("raw", raw_residual), ("detrended", detrended_residual)):
        jb = jarque_bera(values)
        lb = ljung_box(values, lags)
        result[label] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)),
            "skewness": float(skew(values, bias=False)),
            "excess_kurtosis": float(kurtosis(values, fisher=True, bias=False)),
            "jarque_bera_statistic": float(jb.statistic),
            "jarque_bera_p_value": float(jb.pvalue),
            "gaussian_not_rejected_at_alpha": bool(jb.pvalue >= alpha),
            "lag1_autocorrelation": float(autocorrelation(values, 1)[1]),
            "ljung_box": lb,
            "white_not_rejected_at_alpha": bool(lb and all(row["p_value"] >= alpha for row in lb)),
        }
    return result


def trial_quality(
    times: np.ndarray,
    minimum_samples: int,
    minimum_rate_hz: float,
    maximum_gap_s: float,
) -> dict[str, Any]:
    duration = float(times[-1] - times[0])
    gaps = np.diff(times)
    rate = float((len(times) - 1) / duration) if duration > 0.0 else 0.0
    max_gap = float(np.max(gaps)) if len(gaps) else math.inf
    checks = {
        "minimum_samples": len(times) >= minimum_samples,
        "minimum_rate_hz": rate >= minimum_rate_hz,
        "maximum_gap_s": max_gap <= maximum_gap_s,
    }
    return {
        "acceptable": all(checks.values()),
        "checks": checks,
        "sample_count": int(len(times)),
        "span_s": duration,
        "sample_rate_hz": rate,
        "maximum_gap_s": max_gap,
    }


def analyze_trial(
    trial_manifest: dict[str, Any],
    csv_path: Path,
    design: dict[str, Any],
) -> tuple[dict[str, Any], np.ndarray]:
    times, positions = load_pose_csv(csv_path)
    start_s, end_s = [float(v) for v in design["collection"]["analysis_window_s"]]
    times, positions = fixed_window(times, positions, start_s, end_s)
    quality = trial_quality(
        times,
        int(design["collection"]["minimum_analysis_samples"]),
        float(design["collection"]["minimum_analysis_rate_hz"]),
        float(design["collection"]["maximum_analysis_gap_s"]),
    )
    raw_residuals = centered_residuals(positions)
    detrended_residuals, slopes = linear_detrend(times, positions)
    raw_covariance = covariance_from_residuals(raw_residuals)
    detrended_covariance = covariance_from_residuals(detrended_residuals)
    expected = np.asarray(
        [float(trial_manifest["range_m"]), float(trial_manifest["lateral_m"])], dtype=float
    )
    mean = np.mean(positions, axis=0)
    bias = mean - expected
    alpha = float(design["residual_diagnostics"]["gaussianity_alpha"])
    whiteness_alpha = float(design["residual_diagnostics"]["whiteness_alpha"])
    if abs(alpha - whiteness_alpha) > 1.0e-12:
        raise ValueError("G3 v1 requires the same diagnostic alpha for Gaussianity and whiteness")
    lags = [int(v) for v in design["residual_diagnostics"]["whiteness_lags"]]

    capture_summary_path = csv_path.parent / "direct_capture_summary.json"
    capture_summary = (
        json.loads(capture_summary_path.read_text(encoding="utf-8"))
        if capture_summary_path.is_file()
        else None
    )
    report = {
        "trial_id": trial_manifest["trial_id"],
        "condition_id": trial_manifest["condition_id"],
        "range_m": float(trial_manifest["range_m"]),
        "lateral_m": float(trial_manifest["lateral_m"]),
        "yaw_deg": float(trial_manifest["yaw_deg"]),
        "repetition": int(trial_manifest["repetition"]),
        "csv_path": str(csv_path),
        "quality": quality,
        "mean_position_m": mean.tolist(),
        "fixture_referenced_bias_m": bias.tolist(),
        "fixture_uncertainty": trial_manifest.get("truth_uncertainty"),
        "linear_drift_mps": slopes.tolist(),
        "raw_covariance_m2": raw_covariance.tolist(),
        "detrended_covariance_m2": detrended_covariance.tolist(),
        "raw_correlation_xy": correlation_from_covariance(raw_covariance),
        "detrended_correlation_xy": correlation_from_covariance(detrended_covariance),
        "diagnostics": {
            "alpha": alpha,
            "x": axis_diagnostics(raw_residuals[:, 0], detrended_residuals[:, 0], lags, alpha),
            "y": axis_diagnostics(raw_residuals[:, 1], detrended_residuals[:, 1], lags, alpha),
        },
        "capture_summary": capture_summary,
        "interpretation": {
            "measurement_noise": "detrended covariance is the primary candidate short-window measurement dispersion",
            "bias": "mean minus declared fixture position includes camera calibration and fixture placement effects",
            "calibration_separation": "calibration and fixture contributions are not independently identifiable from this trial alone",
        },
    }
    return report, detrended_residuals


def concat_residuals(records: list[dict[str, Any]]) -> np.ndarray:
    return np.concatenate([record["_residuals"] for record in records], axis=0)


def pooled_covariance(records: list[dict[str, Any]]) -> np.ndarray:
    return covariance_from_residuals(concat_residuals(records))


def feature_vector(record: dict[str, Any], model_id: str) -> np.ndarray:
    if model_id == "range_logdiag_fixed_corr":
        return np.asarray([1.0, float(record["range_m"])])
    if model_id == "range_yaw_logdiag_fixed_corr":
        return np.asarray([1.0, float(record["range_m"]), abs(math.radians(float(record["yaw_deg"])))])
    raise ValueError(model_id)


def fit_logdiag_model(records: list[dict[str, Any]], model_id: str) -> dict[str, Any]:
    features = np.vstack([feature_vector(row, model_id) for row in records])
    log_var_x = np.log([max(EPS, float(row["detrended_covariance_m2"][0][0])) for row in records])
    log_var_y = np.log([max(EPS, float(row["detrended_covariance_m2"][1][1])) for row in records])
    beta_x, *_ = np.linalg.lstsq(features, log_var_x, rcond=None)
    beta_y, *_ = np.linalg.lstsq(features, log_var_y, rcond=None)
    rho = correlation_from_covariance(pooled_covariance(records))
    return {"beta_log_var_x": beta_x.tolist(), "beta_log_var_y": beta_y.tolist(), "rho": rho}


def covariance_for_model(
    train: list[dict[str, Any]], held_out: dict[str, Any], model_id: str
) -> tuple[np.ndarray, dict[str, Any]]:
    pooled = pooled_covariance(train)
    if model_id == "constant_full":
        return pooled, {"covariance_m2": pooled.tolist()}
    if model_id in {"range_logdiag_fixed_corr", "range_yaw_logdiag_fixed_corr"}:
        params = fit_logdiag_model(train, model_id)
        feature = feature_vector(held_out, model_id)
        var_x = math.exp(float(np.dot(params["beta_log_var_x"], feature)))
        var_y = math.exp(float(np.dot(params["beta_log_var_y"], feature)))
        rho = float(params["rho"])
        cov_xy = rho * math.sqrt(var_x * var_y)
        return regularize_covariance(np.asarray([[var_x, cov_xy], [cov_xy, var_y]])), params
    if model_id == "condition_shrinkage":
        matching = [row for row in train if row["condition_id"] == held_out["condition_id"]]
        condition_cov = pooled_covariance(matching) if matching else pooled
        covariance = 0.75 * condition_cov + 0.25 * pooled
        return regularize_covariance(covariance), {
            "condition_training_trials": len(matching),
            "shrinkage_to_pooled": 0.25,
        }
    raise ValueError(model_id)


def gaussian_nll(residuals: np.ndarray, covariance: np.ndarray) -> float:
    covariance = regularize_covariance(covariance)
    sign, logdet = np.linalg.slogdet(covariance)
    if sign <= 0:
        return math.inf
    inverse = np.linalg.inv(covariance)
    quadratic = np.einsum("ni,ij,nj->n", residuals, inverse, residuals)
    return float(0.5 * np.sum(2.0 * math.log(2.0 * math.pi) + logdet + quadratic))


def model_complexity(model_id: str, condition_count: int) -> int:
    return {
        "constant_full": 3,
        "range_logdiag_fixed_corr": 5,
        "range_yaw_logdiag_fixed_corr": 7,
        "condition_shrinkage": max(3, 3 * condition_count),
    }[model_id]


def select_covariance_model(records: list[dict[str, Any]], design: dict[str, Any]) -> dict[str, Any]:
    minimum_trials = int(design["model_selection"]["minimum_complete_trials"])
    minimum_ranges = int(design["model_selection"]["minimum_distinct_ranges"])
    distinct_ranges = len({round(float(row["range_m"]), 6) for row in records})
    if len(records) < minimum_trials or distinct_ranges < minimum_ranges:
        covariance = pooled_covariance(records) if records else np.eye(2)
        return {
            "status": "INSUFFICIENT_DATA_FOR_MODEL_SELECTION",
            "selected_model": "constant_full" if records else None,
            "completed_trials": len(records),
            "distinct_ranges": distinct_ranges,
            "constant_covariance_m2": covariance.tolist() if records else None,
            "scores": [],
        }

    candidates = [row["id"] for row in design["candidate_covariance_models"]]
    condition_count = len({row["condition_id"] for row in records})
    total_samples = sum(len(row["_residuals"]) for row in records)
    scores: list[dict[str, Any]] = []
    for model_id in candidates:
        total_nll = 0.0
        fold_details: list[dict[str, Any]] = []
        valid = True
        for index, held_out in enumerate(records):
            train = records[:index] + records[index + 1 :]
            try:
                covariance, _params = covariance_for_model(train, held_out, model_id)
                nll = gaussian_nll(held_out["_residuals"], covariance)
            except Exception as exc:
                valid = False
                fold_details.append({"trial_id": held_out["trial_id"], "error": str(exc)})
                break
            total_nll += nll
            fold_details.append(
                {
                    "trial_id": held_out["trial_id"],
                    "nll": nll,
                    "covariance_m2": covariance.tolist(),
                }
            )
        complexity = model_complexity(model_id, condition_count)
        penalized = 2.0 * total_nll + complexity * math.log(max(total_samples, 2)) if valid else math.inf
        scores.append(
            {
                "model_id": model_id,
                "valid": valid,
                "held_out_nll": total_nll if valid else None,
                "complexity_parameters": complexity,
                "penalized_score": penalized if valid else None,
                "folds": fold_details,
            }
        )

    valid_scores = [row for row in scores if row["valid"] and row["penalized_score"] is not None]
    valid_scores.sort(key=lambda row: float(row["penalized_score"]))
    selected = valid_scores[0]
    if len(valid_scores) > 1:
        best = float(valid_scores[0]["penalized_score"])
        near = [
            row
            for row in valid_scores
            if abs(float(row["penalized_score"]) - best) / max(abs(best), 1.0) < 0.02
        ]
        selected = min(near, key=lambda row: int(row["complexity_parameters"]))

    selected_id = str(selected["model_id"])
    full_reference = records[0]
    full_covariance, full_parameters = covariance_for_model(records, full_reference, selected_id)
    if selected_id in {"range_logdiag_fixed_corr", "range_yaw_logdiag_fixed_corr"}:
        full_parameters = fit_logdiag_model(records, selected_id)
        full_covariance = None
    elif selected_id == "condition_shrinkage":
        full_parameters = {
            condition: (
                0.75 * pooled_covariance([row for row in records if row["condition_id"] == condition])
                + 0.25 * pooled_covariance(records)
            ).tolist()
            for condition in sorted({row["condition_id"] for row in records})
        }
        full_covariance = None

    return {
        "status": "MODEL_SELECTED",
        "selected_model": selected_id,
        "tie_rule": design["model_selection"]["tie_rule"],
        "scores": scores,
        "selected_parameters": full_parameters,
        "selected_reference_covariance_m2": full_covariance.tolist() if full_covariance is not None else None,
    }


def condition_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["condition_id"]].append(row)
    summaries: list[dict[str, Any]] = []
    for condition_id, rows in sorted(grouped.items()):
        covariances = np.asarray([row["detrended_covariance_m2"] for row in rows], dtype=float)
        biases = np.asarray([row["fixture_referenced_bias_m"] for row in rows], dtype=float)
        summaries.append(
            {
                "condition_id": condition_id,
                "range_m": rows[0]["range_m"],
                "yaw_deg": rows[0]["yaw_deg"],
                "trial_count": len(rows),
                "mean_bias_m": np.mean(biases, axis=0).tolist(),
                "mean_detrended_covariance_m2": np.mean(covariances, axis=0).tolist(),
                "covariance_relative_frobenius_span": (
                    float(
                        max(
                            np.linalg.norm(cov - np.mean(covariances, axis=0), ord="fro")
                            / max(np.linalg.norm(np.mean(covariances, axis=0), ord="fro"), EPS)
                            for cov in covariances
                        )
                    )
                    if len(rows) > 1
                    else None
                ),
            }
        )
    return summaries


def locate_accepted_csv(trial_dir: Path, manifest: dict[str, Any]) -> Path | None:
    accepted = manifest.get("accepted_attempt")
    if accepted is None:
        return None
    path = trial_dir / f"attempt_{int(accepted):02d}" / "vision_pose_log.csv"
    return path if path.is_file() else None


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GHOST-X G3 Measurement Characterization",
        "",
        f"Status: **{report['status']}**",
        "",
        f"Completed acceptable trials: `{report['completed_acceptable_trials']}` / `{report['planned_trials']}`",
        f"Completed conditions: `{report['completed_conditions']}` / `{report['planned_conditions']}`",
        "",
        "## Interpretation boundary",
        "",
        "Detrended covariance characterizes short-window camera measurement dispersion. Fixture-referenced bias combines camera calibration error, target placement error, and repeatability. This campaign does not by itself isolate calibration uncertainty or validate dynamic tracker accuracy.",
        "",
        "## Covariance model selection",
        "",
        f"Selection status: `{report['covariance_model_selection']['status']}`",
        f"Selected model: `{report['covariance_model_selection'].get('selected_model')}`",
        "",
    ]
    if report["covariance_model_selection"].get("scores"):
        lines.extend(["| Model | Held-out NLL | Penalized score | Valid |", "|---|---:|---:|:---:|"])
        for row in report["covariance_model_selection"]["scores"]:
            nll = row.get("held_out_nll")
            score = row.get("penalized_score")
            lines.append(
                f"| `{row['model_id']}` | {nll:.3f} | {score:.3f} | {row['valid']} |"
                if nll is not None and score is not None
                else f"| `{row['model_id']}` | — | — | {row['valid']} |"
            )
    lines.extend(["", "## Condition summary", "", "| Condition | Range | Yaw | Trials | Bias x | Bias y |", "|---|---:|---:|---:|---:|---:|"])
    for row in report["condition_summaries"]:
        lines.append(
            f"| `{row['condition_id']}` | {row['range_m']:.2f} m | {row['yaw_deg']:+.0f}° | {row['trial_count']} | {row['mean_bias_m'][0]:+.6f} m | {row['mean_bias_m'][1]:+.6f} m |"
        )
    lines.extend(
        [
            "",
            "## Assumption diagnostics",
            "",
            f"Trials with detrended Gaussianity not rejected on both axes: `{report['diagnostic_counts']['gaussian_not_rejected_both_axes']}`",
            f"Trials with detrended whiteness not rejected on both axes: `{report['diagnostic_counts']['white_not_rejected_both_axes']}`",
            "",
            "Failure to reject is not proof of Gaussianity or whiteness. Rejection must be carried into G6 consistency validity labels.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze_campaign(campaign_dir: Path, out_dir: Path) -> dict[str, Any]:
    campaign = json.loads((campaign_dir / "campaign_manifest.json").read_text(encoding="utf-8"))
    design = yaml.safe_load((campaign_dir / "design_snapshot.yaml").read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    for trial_dir in sorted((campaign_dir / "trials").iterdir()):
        if not trial_dir.is_dir():
            continue
        manifest = json.loads((trial_dir / "trial_manifest.json").read_text(encoding="utf-8"))
        csv_path = locate_accepted_csv(trial_dir, manifest)
        if csv_path is None:
            invalid.append({"trial_id": manifest["trial_id"], "reason": "NO_ACCEPTED_ATTEMPT"})
            continue
        try:
            report, residuals = analyze_trial(manifest, csv_path, design)
        except Exception as exc:
            invalid.append({"trial_id": manifest["trial_id"], "reason": str(exc)})
            continue
        if not report["quality"]["acceptable"]:
            invalid.append({"trial_id": manifest["trial_id"], "reason": "ANALYSIS_QUALITY_GATE_FAILED"})
            continue
        report["_residuals"] = residuals
        records.append(report)

    model_selection = select_covariance_model(records, design)
    condition_summary = condition_summaries(records)
    gaussian_count = sum(
        row["diagnostics"]["x"]["detrended"]["gaussian_not_rejected_at_alpha"]
        and row["diagnostics"]["y"]["detrended"]["gaussian_not_rejected_at_alpha"]
        for row in records
    )
    white_count = sum(
        row["diagnostics"]["x"]["detrended"]["white_not_rejected_at_alpha"]
        and row["diagnostics"]["y"]["detrended"]["white_not_rejected_at_alpha"]
        for row in records
    )
    exit_criteria = design["exit_criteria"]
    complete = (
        len(records) >= int(exit_criteria["minimum_complete_trials"])
        and len(condition_summary) >= int(exit_criteria["minimum_complete_conditions"])
        and model_selection["status"] == "MODEL_SELECTED"
    )
    public_records = [{key: value for key, value in row.items() if key != "_residuals"} for row in records]
    report = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "project": "GHOST-X",
        "phase": "G3_MEASUREMENT_CHARACTERIZATION",
        "campaign_id": campaign["campaign_id"],
        "protocol_version": campaign["protocol_version"],
        "protocol_commit": campaign["protocol_commit"],
        "design_sha256": campaign["design_sha256"],
        "calibration_sha256": campaign["calibration_sha256"],
        "planned_trials": int(campaign["planned_trial_count"]),
        "planned_conditions": int(campaign["condition_count"]),
        "completed_acceptable_trials": len(records),
        "completed_conditions": len(condition_summary),
        "status": "COMPLETE" if complete else "INCOMPLETE_COLLECTION",
        "trial_results": public_records,
        "invalid_or_missing_trials": invalid,
        "condition_summaries": condition_summary,
        "diagnostic_counts": {
            "gaussian_not_rejected_both_axes": int(gaussian_count),
            "white_not_rejected_both_axes": int(white_count),
            "total_trials": len(records),
        },
        "covariance_model_selection": model_selection,
        "uncertainty_separation": {
            "measurement_dispersion": "detrended within-trial residual covariance",
            "fixture_referenced_bias": "trial mean minus declared camera-frame fixture position",
            "fixture_uncertainty": design["truth"],
            "calibration_uncertainty": "not independently identified; remains combined with fixture-referenced bias unless a separate calibration study is supplied",
        },
        "claim_boundary": (
            "Stationary multi-condition camera measurement characterization only. "
            "Does not validate dynamic tracker accuracy or estimator superiority."
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "measurement_characterization.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "measurement_characterization.md").write_text(format_markdown(report), encoding="utf-8")
    with (out_dir / "trial_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "trial_id",
            "condition_id",
            "range_m",
            "yaw_deg",
            "repetition",
            "samples",
            "rate_hz",
            "max_gap_s",
            "bias_x_m",
            "bias_y_m",
            "r_xx_m2",
            "r_xy_m2",
            "r_yy_m2",
            "drift_x_mps",
            "drift_y_mps",
            "gaussian_x",
            "gaussian_y",
            "white_x",
            "white_y",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            cov = row["detrended_covariance_m2"]
            writer.writerow(
                {
                    "trial_id": row["trial_id"],
                    "condition_id": row["condition_id"],
                    "range_m": row["range_m"],
                    "yaw_deg": row["yaw_deg"],
                    "repetition": row["repetition"],
                    "samples": row["quality"]["sample_count"],
                    "rate_hz": row["quality"]["sample_rate_hz"],
                    "max_gap_s": row["quality"]["maximum_gap_s"],
                    "bias_x_m": row["fixture_referenced_bias_m"][0],
                    "bias_y_m": row["fixture_referenced_bias_m"][1],
                    "r_xx_m2": cov[0][0],
                    "r_xy_m2": cov[0][1],
                    "r_yy_m2": cov[1][1],
                    "drift_x_mps": row["linear_drift_mps"][0],
                    "drift_y_mps": row["linear_drift_mps"][1],
                    "gaussian_x": row["diagnostics"]["x"]["detrended"]["gaussian_not_rejected_at_alpha"],
                    "gaussian_y": row["diagnostics"]["y"]["detrended"]["gaussian_not_rejected_at_alpha"],
                    "white_x": row["diagnostics"]["x"]["detrended"]["white_not_rejected_at_alpha"],
                    "white_y": row["diagnostics"]["y"]["detrended"]["white_not_rejected_at_alpha"],
                }
            )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_campaign(args.campaign_dir.expanduser().resolve(), args.out_dir.expanduser().resolve())
    print(
        json.dumps(
            {
                "status": report["status"],
                "completed_trials": report["completed_acceptable_trials"],
                "completed_conditions": report["completed_conditions"],
                "selected_model": report["covariance_model_selection"].get("selected_model"),
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
