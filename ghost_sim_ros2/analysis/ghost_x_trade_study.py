"""Deterministic GHOST-X G7 estimator parameter trade study."""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Callable

import numpy as np
import yaml
from scipy.stats import chi2

from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.ghost_mh_mode_bank import mode_bank
from analysis.imm_live_bridge import FormalImmLiveAdapter, FormalImmLiveConfig


OVERCONFIDENT_NEES_THRESHOLD = float(chi2.ppf(0.975, 2))


@dataclass(frozen=True)
class TrialStream:
    trial_id: str
    scenario_family: str
    rows: list[dict[str, Any]]


def load_design(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("trade-study design must be a mapping")
    return value


def load_streams(campaign_dir: Path) -> list[TrialStream]:
    streams: list[TrialStream] = []
    for path in sorted((campaign_dir / "canonical_streams").glob("*.jsonl")):
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"non-object row in {path}")
                rows.append(value)
        if not rows:
            raise ValueError(f"empty stream: {path}")
        streams.append(TrialStream(path.stem, str(rows[0]["scenario_family"]), rows))
    if not streams:
        raise ValueError("no canonical streams found")
    return streams


def imm_candidates(design: dict[str, Any]) -> list[dict[str, Any]]:
    section = design["imm"]
    candidates = []
    for stay, smooth, maneuver in product(
        section["transition_stay_probability"],
        section["smooth_acceleration_std_mps2"],
        section["maneuver_acceleration_std_mps2"],
    ):
        candidates.append(
            {
                "transition_stay_probability": float(stay),
                "smooth_acceleration_std_mps2": float(smooth),
                "maneuver_acceleration_std_mps2": float(maneuver),
                "future_horizon_s": 1.0,
            }
        )
    return candidates


def mh_candidates(design: dict[str, Any]) -> list[dict[str, Any]]:
    section = design["mh"]
    levels = {
        "model_count": section["model_count"],
        "gate_chi2": section["gate_chi2"],
        "max_occlusion_s": section["max_occlusion_s"],
        "stationary_prior_scale": section["stationary_prior_scale"],
    }
    candidates = []
    # Balanced 27-run reduced factorial. Each level appears nine times per factor.
    for run in range(27):
        a = run % 3
        b = (run // 3) % 3
        block = (run // 9) % 3
        c = (a + b + block) % 3
        d = (a + 2 * b + block) % 3
        candidates.append(
            {
                "model_count": int(levels["model_count"][a]),
                "gate_chi2": float(levels["gate_chi2"][b]),
                "max_occlusion_s": float(levels["max_occlusion_s"][c]),
                "stationary_prior_scale": float(levels["stationary_prior_scale"][d]),
                "future_horizon_s": 1.0,
            }
        )
    unique = {json.dumps(candidate, sort_keys=True) for candidate in candidates}
    if len(unique) != len(candidates):
        raise RuntimeError("balanced design produced duplicate candidates")
    return candidates


def evaluate_imm(candidate: dict[str, Any], streams: list[TrialStream]) -> dict[str, Any]:
    stay = float(candidate["transition_stay_probability"])
    transition = ((stay, 1.0 - stay), (1.0 - stay, stay))

    def factory(r: np.ndarray, dt: float):
        return FormalImmLiveAdapter(
            FormalImmLiveConfig(
                dt_s=dt,
                measurement_std_m=math.sqrt(float(r[0, 0])),
                measurement_covariance_xy=tuple(tuple(float(v) for v in row) for row in r),
                smooth_acceleration_std_mps2=float(candidate["smooth_acceleration_std_mps2"]),
                maneuver_acceleration_std_mps2=float(candidate["maneuver_acceleration_std_mps2"]),
                transition_probabilities=transition,
                future_horizon_s=max(0.1, float(candidate["future_horizon_s"])),
                future_dt_s=0.1,
                dropout_degraded_after_steps=5,
            )
        )

    return _evaluate_candidate("formal_imm", candidate, streams, factory, _step_imm)


def evaluate_mh(candidate: dict[str, Any], streams: list[TrialStream]) -> dict[str, Any]:
    def factory(r: np.ndarray, _dt: float):
        models = mode_bank()[: int(candidate["model_count"])]
        adjusted = []
        total = 0.0
        for model in models:
            prior = float(model.prior)
            if model.name == "brake_or_hover":
                prior *= float(candidate["stationary_prior_scale"])
            adjusted.append((model, prior))
            total += prior
        if total <= 0.0:
            raise ValueError("model priors sum nonpositive")
        rebuilt = [
            type(model)(
                model.name,
                ax_mps2=model.ax_mps2,
                ay_mps2=model.ay_mps2,
                speed_scale=model.speed_scale,
                process_accel_std_mps2=model.process_accel_std_mps2,
                prior=prior / total,
            )
            for model, prior in adjusted
        ]
        return CalibratedModeBankTracker(
            models=rebuilt,
            measurement_std_m=math.sqrt(float(r[0, 0])),
            measurement_covariance_xy=r,
            gate_chi2=float(candidate["gate_chi2"]),
            max_occlusion_s=float(candidate["max_occlusion_s"]),
            max_workspace_range_m=100.0,
            allow_signed_local_coordinates=True,
            accel_temperature=0.30,
        )

    return _evaluate_candidate("ghost_mh", candidate, streams, factory, _step_mh)


def _step_imm(estimator: FormalImmLiveAdapter, dt: float, measurement: list[float] | None) -> dict[str, Any]:
    if abs(dt - estimator.config.dt_s) > 1e-12:
        raise ValueError("canonical stream dt changed within trial")
    output = estimator.step(measurement)
    if not output.initialized or output.estimate is None:
        return {"initialized": False, "reset": False}
    estimate = output.estimate
    covariance = np.array(
        [
            [estimate["cov_xx"], estimate["cov_xy"]],
            [estimate["cov_xy"], estimate["cov_yy"]],
        ],
        dtype=float,
    )
    return {
        "initialized": True,
        "reset": False,
        "x": float(estimate["x_m"]),
        "y": float(estimate["y_m"]),
        "vx": float(estimate["vx_mps"]),
        "vy": float(estimate["vy_mps"]),
        "position_covariance": covariance,
        "dynamic_probability": float(output.mode_probabilities.get("maneuver_cv", 0.0)),
    }


def _step_mh(estimator: CalibratedModeBankTracker, dt: float, measurement: list[float] | None) -> dict[str, Any]:
    was_initialized = estimator.initialized
    estimator.step(dt, measurement)
    estimate = estimator.estimate()
    if not estimate.initialized:
        return {"initialized": False, "reset": bool(was_initialized)}
    weights = {hyp.model: float(hyp.weight) for hyp in estimator.top_hypotheses(8)}
    dynamic_probability = 1.0 - float(weights.get("constant_velocity", weights.get("visible_cv", 1.0)))
    return {
        "initialized": True,
        "reset": False,
        "x": float(estimate.x[0, 0]),
        "y": float(estimate.x[1, 0]),
        "vx": float(estimate.x[2, 0]),
        "vy": float(estimate.x[3, 0]),
        "position_covariance": np.asarray(estimate.p[:2, :2], dtype=float),
        "dynamic_probability": min(1.0, max(0.0, dynamic_probability)),
    }


def _evaluate_candidate(
    estimator_name: str,
    candidate: dict[str, Any],
    streams: list[TrialStream],
    factory: Callable[[np.ndarray, float], Any],
    step_function: Callable[[Any, float, list[float] | None], dict[str, Any]],
) -> dict[str, Any]:
    squared_errors: list[float] = []
    hidden_squared_errors: list[float] = []
    future_squared_errors: list[float] = []
    nees_values: list[float] = []
    brier_values: list[float] = []
    step_times_us: list[float] = []
    reset_count = 0
    nonfinite_count = 0
    total_steps = 0
    initialized_steps = 0
    scenario_metrics: dict[str, list[float]] = {}
    horizon = float(candidate["future_horizon_s"])

    for stream in streams:
        rows = stream.rows
        r = np.asarray(rows[0]["measurement_covariance_xy_m2"], dtype=float)
        dt = float(rows[0]["dt_s"])
        estimator = factory(r, dt)
        trial_errors: list[float] = []
        previous_truth_velocity: np.ndarray | None = None
        initialized_once = False
        for index, row in enumerate(rows):
            total_steps += 1
            visible = bool(row.get("visible"))
            measurement = row.get("measurement_xy_m") if visible else None
            start_ns = time.perf_counter_ns()
            output = step_function(estimator, float(row["dt_s"]), measurement)
            step_times_us.append((time.perf_counter_ns() - start_ns) / 1000.0)
            if output.get("reset"):
                reset_count += 1
            if not output.get("initialized"):
                continue
            initialized_steps += 1
            initialized_once = True
            values = np.array([output["x"], output["y"], output["vx"], output["vy"]], dtype=float)
            covariance = np.asarray(output["position_covariance"], dtype=float)
            if not np.isfinite(values).all() or covariance.shape != (2, 2) or not np.isfinite(covariance).all():
                nonfinite_count += 1
                continue
            truth = row["truth"]
            truth_position = np.array([truth["x_m"], truth["y_m"]], dtype=float)
            error = float(np.linalg.norm(values[:2] - truth_position))
            squared_errors.append(error * error)
            trial_errors.append(error)
            if not visible:
                hidden_squared_errors.append(error * error)
            position_error = values[:2] - truth_position
            nees = _quadratic(position_error, covariance)
            if nees is not None:
                nees_values.append(nees)

            truth_velocity = np.array([truth["vx_mps"], truth["vy_mps"]], dtype=float)
            acceleration = 0.0 if previous_truth_velocity is None else float(np.linalg.norm(truth_velocity - previous_truth_velocity) / dt)
            previous_truth_velocity = truth_velocity
            active_dynamic = 1.0 if acceleration >= 0.15 else 0.0
            probability = min(1.0, max(0.0, float(output.get("dynamic_probability", 0.0))))
            brier_values.append((probability - active_dynamic) ** 2)

            future_index = index + int(round(horizon / dt))
            if future_index < len(rows) and (not visible or not any(not bool(item.get("visible")) for item in rows)):
                future_truth = rows[future_index]["truth"]
                predicted = values[:2] + values[2:] * horizon
                future_error = float(
                    np.linalg.norm(predicted - np.array([future_truth["x_m"], future_truth["y_m"]], dtype=float))
                )
                future_squared_errors.append(future_error * future_error)
        if initialized_once and trial_errors:
            scenario_metrics.setdefault(stream.scenario_family, []).append(float(math.sqrt(statistics.fmean(v * v for v in trial_errors))))

    rmse_all = _rmse_from_squared(squared_errors)
    rmse_hidden = _rmse_from_squared(hidden_squared_errors) if hidden_squared_errors else rmse_all
    future_rmse = _rmse_from_squared(future_squared_errors) if future_squared_errors else rmse_all
    reset_rate = reset_count / max(1, total_steps)
    overconfidence = sum(value > OVERCONFIDENT_NEES_THRESHOLD for value in nees_values) / max(1, len(nees_values))
    compute_us = float(statistics.fmean(step_times_us)) if step_times_us else float("inf")
    brier = float(statistics.fmean(brier_values)) if brier_values else 1.0
    future_per_second = future_rmse / max(horizon, 1e-9)
    score = (
        rmse_all
        + 1.5 * rmse_hidden
        + 0.5 * future_per_second
        + 0.10 * overconfidence
        + 0.10 * brier
        + 0.00002 * compute_us
        + 5.0 * reset_rate
    )
    valid = nonfinite_count == 0 and reset_rate <= 0.0 and math.isfinite(score)
    return {
        "estimator": estimator_name,
        "candidate": candidate,
        "valid": valid,
        "score": float(score),
        "position_rmse_m": rmse_all,
        "hidden_position_rmse_m": rmse_hidden,
        "future_rmse_m": future_rmse,
        "future_rmse_per_second": future_per_second,
        "position_error_p95_m": _percentile_from_squared(squared_errors, 95.0),
        "mean_position_nees": float(statistics.fmean(nees_values)) if nees_values else None,
        "overconfidence_fraction": float(overconfidence),
        "dynamic_probability_brier_score": brier,
        "compute_us_per_step": compute_us,
        "reset_count": reset_count,
        "reset_rate": reset_rate,
        "nonfinite_count": nonfinite_count,
        "total_steps": total_steps,
        "initialized_steps": initialized_steps,
        "scenario_rmse_m": {name: float(statistics.fmean(values)) for name, values in sorted(scenario_metrics.items())},
    }


def select_candidate(results: list[dict[str, Any]], tie_fraction: float, complexity_key: Callable[[dict[str, Any]], tuple]) -> dict[str, Any]:
    valid = [result for result in results if result["valid"]]
    if not valid:
        raise RuntimeError("no valid candidates")
    best_score = min(float(result["score"]) for result in valid)
    tied = [result for result in valid if float(result["score"]) <= best_score * (1.0 + tie_fraction)]
    return min(tied, key=lambda result: complexity_key(result["candidate"]) + (float(result["compute_us_per_step"]), float(result["score"])))


def choose_horizon(
    base_candidate: dict[str, Any],
    horizons: list[float],
    evaluator: Callable[[dict[str, Any]], dict[str, Any]],
    threshold_m: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    results = []
    for horizon in sorted(float(value) for value in horizons):
        candidate = dict(base_candidate)
        candidate["future_horizon_s"] = horizon
        results.append(evaluator(candidate))
    acceptable = [result for result in results if result["valid"] and result["future_rmse_m"] <= threshold_m]
    selected = max(acceptable, key=lambda result: float(result["candidate"]["future_horizon_s"])) if acceptable else min(results, key=lambda result: result["future_rmse_m"])
    return selected, results


def run_trade_study(design_path: Path, campaign_dir: Path) -> dict[str, Any]:
    design = load_design(design_path)
    streams = load_streams(campaign_dir)
    tie_fraction = float(design["selection"]["simpler_model_tie_fraction"])
    threshold = float(design["selection"]["future_rmse_threshold_m"])

    imm_results = [evaluate_imm(candidate, streams) for candidate in imm_candidates(design)]
    selected_imm_core = select_candidate(
        imm_results,
        tie_fraction,
        lambda candidate: (
            abs(float(candidate["transition_stay_probability"]) - 0.97),
            abs(float(candidate["smooth_acceleration_std_mps2"]) - 0.015),
            abs(float(candidate["maneuver_acceleration_std_mps2"]) - 0.75),
        ),
    )
    selected_imm, imm_horizon_results = choose_horizon(
        selected_imm_core["candidate"],
        design["imm"]["future_horizon_s"],
        lambda candidate: evaluate_imm(candidate, streams),
        threshold,
    )

    mh_results = [evaluate_mh(candidate, streams) for candidate in mh_candidates(design)]
    selected_mh_core = select_candidate(
        mh_results,
        tie_fraction,
        lambda candidate: (int(candidate["model_count"]),),
    )
    selected_mh, mh_horizon_results = choose_horizon(
        selected_mh_core["candidate"],
        design["mh"]["future_horizon_s"],
        lambda candidate: evaluate_mh(candidate, streams),
        threshold,
    )

    return {
        "schema_version": 1,
        "phase": "G7_MULTI_MODEL_AND_HYPOTHESIS_TRADE_STUDY",
        "campaign_dir": str(campaign_dir.resolve()),
        "canonical_trials": len(streams),
        "predeclared_design": str(design_path.resolve()),
        "score_formula": design["selection"]["score_formula"],
        "simpler_model_tie_fraction": tie_fraction,
        "imm": {
            "candidate_count": len(imm_results),
            "selected": selected_imm,
            "core_candidates": sorted(imm_results, key=lambda result: result["score"]),
            "horizon_sweep": imm_horizon_results,
        },
        "ghost_mh": {
            "candidate_count": len(mh_results),
            "design": design["mh"]["design"],
            "selected": selected_mh,
            "core_candidates": sorted(mh_results, key=lambda result: result["score"]),
            "horizon_sweep": mh_horizon_results,
        },
        "selection_status": "SYNTHETIC_CANDIDATE_CONFIGURATION_PENDING_PHYSICAL_CONFIRMATION",
        "limitations": [
            "Selected values optimize the frozen synthetic campaign, not the uncollected physical campaign.",
            "The GHOST-MH reduced factorial is balanced but does not estimate every high-order interaction.",
            "Probability calibration labels are derived from deterministic truth acceleration and are not semantic maneuver labels.",
            "Future errors use constant-velocity projection of the current state for a common comparison contract.",
        ],
    }


def write_outputs(report: dict[str, Any], out_dir: Path, selected_config_path: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "GHOST_X_G7_TRADE_STUDY.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out_dir / "GHOST_X_G7_TRADE_STUDY.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "estimator",
                "rank",
                "valid",
                "score",
                "position_rmse_m",
                "hidden_position_rmse_m",
                "future_rmse_m",
                "p95_error_m",
                "overconfidence_fraction",
                "brier_score",
                "compute_us_per_step",
                "candidate_json",
            ]
        )
        for section_name, estimator_name in (("imm", "formal_imm"), ("ghost_mh", "ghost_mh")):
            for rank, result in enumerate(report[section_name]["core_candidates"], start=1):
                writer.writerow(
                    [
                        estimator_name,
                        rank,
                        result["valid"],
                        result["score"],
                        result["position_rmse_m"],
                        result["hidden_position_rmse_m"],
                        result["future_rmse_m"],
                        result["position_error_p95_m"],
                        result["overconfidence_fraction"],
                        result["dynamic_probability_brier_score"],
                        result["compute_us_per_step"],
                        json.dumps(result["candidate"], sort_keys=True),
                    ]
                )

    selected = {
        "schema_version": 1,
        "status": "SYNTHETIC_SELECTED_PENDING_PHYSICAL_CONFIRMATION",
        "formal_imm": report["imm"]["selected"]["candidate"],
        "ghost_mh": report["ghost_mh"]["selected"]["candidate"],
        "source_report": "docs/GHOST_X_G7_TRADE_STUDY.json",
    }
    selected_config_path.parent.mkdir(parents=True, exist_ok=True)
    selected_config_path.write_text(yaml.safe_dump(selected, sort_keys=False), encoding="utf-8")

    lines = [
        "# GHOST-X G7 Multi-Model and Hypothesis Trade Study",
        "",
        f"Canonical trials: `{report['canonical_trials']}`",
        f"IMM candidates: `{report['imm']['candidate_count']}`",
        f"GHOST-MH candidates: `{report['ghost_mh']['candidate_count']}`",
        "",
        "## Selected synthetic candidates",
        "",
    ]
    for section, title in (("imm", "Formal IMM"), ("ghost_mh", "GHOST-MH")):
        result = report[section]["selected"]
        lines.extend(
            [
                f"### {title}",
                "",
                f"- Parameters: `{json.dumps(result['candidate'], sort_keys=True)}`",
                f"- Score: `{result['score']:.6f}`",
                f"- Position RMSE: `{result['position_rmse_m']:.4f} m`",
                f"- Hidden RMSE: `{result['hidden_position_rmse_m']:.4f} m`",
                f"- Future RMSE: `{result['future_rmse_m']:.4f} m`",
                f"- Mean compute: `{result['compute_us_per_step']:.2f} us/step`",
                "",
            ]
        )
    lines.extend(
        [
            "## Claim boundary",
            "",
            "These are synthetic candidate parameters. Hardware measurement characterization and controlled physical truth must confirm or replace them before public physical-performance claims.",
            "",
        ]
    )
    (out_dir / "GHOST_X_G7_TRADE_STUDY.md").write_text("\n".join(lines), encoding="utf-8")


def _quadratic(error: np.ndarray, covariance: np.ndarray) -> float | None:
    covariance = 0.5 * (covariance + covariance.T)
    try:
        factor = np.linalg.cholesky(covariance)
        whitened = np.linalg.solve(factor, error.reshape(-1, 1))
    except np.linalg.LinAlgError:
        return None
    value = float((whitened.T @ whitened)[0, 0])
    return value if math.isfinite(value) else None


def _rmse_from_squared(values: list[float]) -> float:
    return float(math.sqrt(statistics.fmean(values))) if values else float("inf")


def _percentile_from_squared(values: list[float], percentile: float) -> float:
    if not values:
        return float("inf")
    return float(np.percentile(np.sqrt(np.asarray(values, dtype=float)), percentile))
