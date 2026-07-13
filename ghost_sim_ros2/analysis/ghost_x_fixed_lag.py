"""GHOST-X G11 fixed-lag Rauch-Tung-Striebel smoothing study."""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import yaml


H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)


@dataclass(frozen=True)
class Stream:
    trial_id: str
    scenario_family: str
    repeat: int
    rows: list[dict[str, Any]]


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fixed-lag configuration must be a mapping")
    return value


def load_streams(campaign_dir: Path) -> list[Stream]:
    streams = []
    for path in sorted((campaign_dir / "canonical_streams").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            raise ValueError(f"empty stream: {path}")
        streams.append(
            Stream(
                trial_id=path.stem,
                scenario_family=str(rows[0]["scenario_family"]),
                repeat=int(rows[0]["repeat"]),
                rows=rows,
            )
        )
    if not streams:
        raise ValueError("no canonical streams found")
    return streams


def transition(dt_s: float) -> np.ndarray:
    dt = float(dt_s)
    return np.array(
        [[1.0, 0.0, dt, 0.0], [0.0, 1.0, 0.0, dt], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=float,
    )


def process_noise(dt_s: float, acceleration_std_mps2: float) -> np.ndarray:
    dt = float(dt_s)
    sigma2 = float(acceleration_std_mps2) ** 2
    return sigma2 * np.array(
        [
            [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
            [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
            [dt**3 / 2.0, 0.0, dt**2, 0.0],
            [0.0, dt**3 / 2.0, 0.0, dt**2],
        ],
        dtype=float,
    )


def _symmetrize(matrix: np.ndarray) -> np.ndarray:
    return 0.5 * (matrix + matrix.T)


def _update(x_pred: np.ndarray, p_pred: np.ndarray, measurement: np.ndarray, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    innovation = measurement - H @ x_pred
    s = _symmetrize(H @ p_pred @ H.T + r)
    gain = np.linalg.solve(s.T, (p_pred @ H.T).T).T
    x = x_pred + gain @ innovation
    joseph = np.eye(4) - gain @ H
    p = _symmetrize(joseph @ p_pred @ joseph.T + gain @ r @ gain.T)
    return x, p


def fixed_lag_smooth(
    rows: list[dict[str, Any]],
    *,
    lag_steps: int,
    acceleration_std_mps2: float,
) -> dict[str, Any]:
    lag = int(lag_steps)
    if lag < 0:
        raise ValueError("lag_steps must be nonnegative")
    if acceleration_std_mps2 <= 0.0:
        raise ValueError("acceleration_std_mps2 must be positive")
    r = np.asarray(rows[0]["measurement_covariance_xy_m2"], dtype=float)
    filtered_x: list[np.ndarray | None] = []
    filtered_p: list[np.ndarray | None] = []
    predicted_x: list[np.ndarray | None] = []
    predicted_p: list[np.ndarray | None] = []
    transitions: list[np.ndarray | None] = []
    outputs: dict[int, dict[str, Any]] = {}
    initialized = False
    x = np.zeros(4, dtype=float)
    p = np.diag([0.04, 0.04, 0.8, 0.8])
    compute_us: list[float] = []

    for index, row in enumerate(rows):
        start_ns = time.perf_counter_ns()
        dt = float(row["dt_s"])
        f = transition(dt)
        q = process_noise(dt, acceleration_std_mps2)
        measurement = row.get("measurement_xy_m") if bool(row.get("visible")) else None
        if not initialized:
            if measurement is None:
                filtered_x.append(None)
                filtered_p.append(None)
                predicted_x.append(None)
                predicted_p.append(None)
                transitions.append(None)
                compute_us.append((time.perf_counter_ns() - start_ns) / 1000.0)
                continue
            z = np.asarray(measurement, dtype=float)
            x = np.array([z[0], z[1], 0.0, 0.0], dtype=float)
            p = np.diag([0.04, 0.04, 0.8, 0.8])
            initialized = True
            x_pred = x.copy()
            p_pred = p.copy()
        else:
            x_pred = f @ x
            p_pred = _symmetrize(f @ p @ f.T + q)
            if measurement is not None:
                x, p = _update(x_pred, p_pred, np.asarray(measurement, dtype=float), r)
            else:
                x, p = x_pred, p_pred
        filtered_x.append(x.copy())
        filtered_p.append(p.copy())
        predicted_x.append(x_pred.copy())
        predicted_p.append(p_pred.copy())
        transitions.append(f.copy())

        if initialized:
            start = max(0, index - lag)
            while start < index and filtered_x[start] is None:
                start += 1
            smooth_x = filtered_x[index].copy() if filtered_x[index] is not None else None
            smooth_p = filtered_p[index].copy() if filtered_p[index] is not None else None
            if smooth_x is not None and smooth_p is not None:
                for cursor in range(index - 1, start - 1, -1):
                    if filtered_x[cursor] is None or filtered_p[cursor] is None:
                        break
                    next_pred_p = predicted_p[cursor + 1]
                    next_pred_x = predicted_x[cursor + 1]
                    next_f = transitions[cursor + 1]
                    if next_pred_p is None or next_pred_x is None or next_f is None:
                        break
                    try:
                        smoother_gain = np.linalg.solve(next_pred_p.T, (filtered_p[cursor] @ next_f.T).T).T
                    except np.linalg.LinAlgError:
                        break
                    smooth_x = filtered_x[cursor] + smoother_gain @ (smooth_x - next_pred_x)
                    smooth_p = _symmetrize(
                        filtered_p[cursor] + smoother_gain @ (smooth_p - next_pred_p) @ smoother_gain.T
                    )
                if index >= lag or lag == 0:
                    output_index = index - lag if lag > 0 else index
                    outputs[output_index] = {
                        "state": smooth_x.copy(),
                        "covariance": smooth_p.copy(),
                        "available_at_index": index,
                        "effective_lag_steps": index - output_index,
                    }
        compute_us.append((time.perf_counter_ns() - start_ns) / 1000.0)

    return {"outputs": outputs, "compute_us": compute_us}


def apply_ood(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    scale = float(config["measurement_noise_scale"])
    period = int(config["additional_dropout_period_steps"])
    length = int(config["additional_dropout_length_steps"])
    transformed = []
    for index, source in enumerate(rows):
        row = json.loads(json.dumps(source))
        if bool(row.get("visible")) and row.get("measurement_xy_m") is not None:
            truth = np.array([row["truth"]["x_m"], row["truth"]["y_m"]], dtype=float)
            measurement = np.asarray(row["measurement_xy_m"], dtype=float)
            altered = truth + scale * (measurement - truth)
            row["measurement_xy_m"] = [float(altered[0]), float(altered[1])]
        if period > 0 and index % period < length:
            row["visible"] = False
            row["measurement_xy_m"] = None
        transformed.append(row)
    return transformed


def evaluate_candidate(
    streams: list[Stream],
    *,
    lag_steps: int,
    acceleration_std_mps2: float,
    ood_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    squared_errors: list[float] = []
    hidden_squared_errors: list[float] = []
    compute_us: list[float] = []
    trial_rmse: dict[str, float] = {}
    covariance_failures = 0
    for stream in streams:
        rows = apply_ood(stream.rows, ood_config) if ood_config is not None else stream.rows
        result = fixed_lag_smooth(
            rows,
            lag_steps=lag_steps,
            acceleration_std_mps2=acceleration_std_mps2,
        )
        compute_us.extend(result["compute_us"])
        trial_errors = []
        for index, output in result["outputs"].items():
            state = np.asarray(output["state"], dtype=float)
            covariance = np.asarray(output["covariance"], dtype=float)
            if not np.isfinite(state).all() or not np.isfinite(covariance).all():
                covariance_failures += 1
                continue
            if np.min(np.linalg.eigvalsh(_symmetrize(covariance))) < -1e-8:
                covariance_failures += 1
                continue
            truth = rows[index]["truth"]
            error = float(math.hypot(state[0] - float(truth["x_m"]), state[1] - float(truth["y_m"])))
            squared_errors.append(error * error)
            trial_errors.append(error * error)
            if not bool(rows[index].get("visible")):
                hidden_squared_errors.append(error * error)
        if trial_errors:
            trial_rmse[stream.trial_id] = float(math.sqrt(statistics.fmean(trial_errors)))
    dt = float(streams[0].rows[0]["dt_s"])
    position_rmse = _rmse(squared_errors)
    hidden_rmse = _rmse(hidden_squared_errors) if hidden_squared_errors else position_rmse
    latency_s = int(lag_steps) * dt
    mean_compute = float(statistics.fmean(compute_us)) if compute_us else float("inf")
    score = position_rmse + 1.5 * hidden_rmse + 0.02 * latency_s + 0.00002 * mean_compute
    return {
        "lag_steps": int(lag_steps),
        "latency_s": latency_s,
        "acceleration_std_mps2": float(acceleration_std_mps2),
        "position_rmse_m": position_rmse,
        "hidden_rmse_m": hidden_rmse,
        "position_error_p95_m": _percentile(squared_errors, 95.0),
        "compute_us_per_step": mean_compute,
        "compute_p99_us": float(np.percentile(np.asarray(compute_us), 99.0)) if compute_us else None,
        "covariance_failure_count": covariance_failures,
        "score": score,
        "valid": covariance_failures == 0 and math.isfinite(score),
        "trial_rmse_m": trial_rmse,
    }


def select_candidate(results: list[dict[str, Any]], tie_fraction: float) -> dict[str, Any]:
    valid = [result for result in results if result["valid"]]
    if not valid:
        raise RuntimeError("no valid smoother candidate")
    best = min(float(result["score"]) for result in valid)
    tied = [result for result in valid if float(result["score"]) <= best * (1.0 + tie_fraction)]
    return min(
        tied,
        key=lambda result: (
            int(result["lag_steps"]),
            abs(float(result["acceleration_std_mps2"]) - 0.65),
            float(result["compute_us_per_step"]),
        ),
    )


def paired_bootstrap(
    baseline: dict[str, float],
    advanced: dict[str, float],
    *,
    seed: int = 26071311,
    samples: int = 4000,
) -> dict[str, Any]:
    common = sorted(set(baseline) & set(advanced))
    differences = [advanced[key] - baseline[key] for key in common]
    if not differences:
        return {"n_trials": 0, "median_advanced_minus_baseline_m": None, "ci_95_m": None}
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(samples):
        chosen = rng.integers(0, len(differences), size=len(differences))
        boot.append(float(np.median([differences[index] for index in chosen])))
    return {
        "n_trials": len(differences),
        "median_advanced_minus_baseline_m": float(np.median(differences)),
        "ci_95_m": {"low": float(np.percentile(boot, 2.5)), "high": float(np.percentile(boot, 97.5))},
        "negative_favors_fixed_lag": True,
    }


def run_study(config_path: Path, campaign_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    streams = load_streams(campaign_dir)
    split = config["split"]
    tuning = [stream for stream in streams if stream.repeat == int(split["tuning_repeat"])]
    evaluation = [stream for stream in streams if stream.repeat == int(split["frozen_evaluation_repeat"])]
    ood = [stream for stream in streams if stream.repeat == int(split["out_of_distribution_repeat"])]
    if not tuning or not evaluation or not ood:
        raise ValueError("frozen split is incomplete")

    ablation = []
    for lag, acceleration in product(config["ablation"]["lag_steps"], config["ablation"]["acceleration_std_mps2"]):
        ablation.append(
            evaluate_candidate(
                tuning,
                lag_steps=int(lag),
                acceleration_std_mps2=float(acceleration),
            )
        )
    selected = select_candidate(ablation, float(config["selection"]["simpler_tie_fraction"]))
    selected_parameters = {
        "lag_steps": int(selected["lag_steps"]),
        "acceleration_std_mps2": float(selected["acceleration_std_mps2"]),
    }
    baseline_parameters = {"lag_steps": 0, "acceleration_std_mps2": 0.65}
    baseline_eval = evaluate_candidate(evaluation, **baseline_parameters)
    selected_eval = evaluate_candidate(evaluation, **selected_parameters)
    baseline_ood = evaluate_candidate(ood, **baseline_parameters, ood_config=config["out_of_distribution"])
    selected_ood = evaluate_candidate(ood, **selected_parameters, ood_config=config["out_of_distribution"])

    return {
        "schema_version": 1,
        "phase": "G11_FIXED_LAG_SMOOTHER",
        "campaign_dir": str(campaign_dir.resolve()),
        "split": split,
        "ablation_count": len(ablation),
        "ablation": sorted(ablation, key=lambda result: result["score"]),
        "selected_parameters": selected_parameters,
        "selected_tuning_result": selected,
        "classical_baseline_parameters": baseline_parameters,
        "frozen_evaluation": {
            "baseline": baseline_eval,
            "fixed_lag": selected_eval,
            "paired_bootstrap": paired_bootstrap(baseline_eval["trial_rmse_m"], selected_eval["trial_rmse_m"]),
        },
        "out_of_distribution": {
            "transformation": config["out_of_distribution"],
            "baseline": baseline_ood,
            "fixed_lag": selected_ood,
            "paired_bootstrap": paired_bootstrap(baseline_ood["trial_rmse_m"], selected_ood["trial_rmse_m"], seed=26071312),
        },
        "classical_baseline_retained": True,
        "claim_boundary": "OFFLINE_FIXED_LAG_SMOOTHER_NOT_A_CAUSAL_ZERO_LATENCY_LIVE_ESTIMATOR",
    }


def write_outputs(report: dict[str, Any], out_dir: Path, selected_config_path: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "GHOST_X_G11_FIXED_LAG.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out_dir / "GHOST_X_G11_FIXED_LAG.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["rank", "lag_steps", "latency_s", "acceleration_std_mps2", "position_rmse_m", "hidden_rmse_m", "compute_us_per_step", "score", "valid"])
        for rank, result in enumerate(report["ablation"], start=1):
            writer.writerow(
                [
                    rank,
                    result["lag_steps"],
                    result["latency_s"],
                    result["acceleration_std_mps2"],
                    result["position_rmse_m"],
                    result["hidden_rmse_m"],
                    result["compute_us_per_step"],
                    result["score"],
                    result["valid"],
                ]
            )
    selected_config_path.parent.mkdir(parents=True, exist_ok=True)
    selected_config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "status": "FROZEN_SYNTHETIC_SELECTION",
                **report["selected_parameters"],
                "source_report": "docs/GHOST_X_G11_FIXED_LAG.json",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    evaluation = report["frozen_evaluation"]
    ood = report["out_of_distribution"]
    lines = [
        "# GHOST-X G11 Fixed-Lag Smoother",
        "",
        f"Selected: `{json.dumps(report['selected_parameters'], sort_keys=True)}`",
        f"Ablation candidates: `{report['ablation_count']}`",
        "",
        "| Set | Baseline RMSE (m) | Fixed-lag RMSE (m) | Baseline hidden (m) | Fixed-lag hidden (m) |",
        "|---|---:|---:|---:|---:|",
        f"| Frozen evaluation | {evaluation['baseline']['position_rmse_m']:.4f} | {evaluation['fixed_lag']['position_rmse_m']:.4f} | {evaluation['baseline']['hidden_rmse_m']:.4f} | {evaluation['fixed_lag']['hidden_rmse_m']:.4f} |",
        f"| OOD | {ood['baseline']['position_rmse_m']:.4f} | {ood['fixed_lag']['position_rmse_m']:.4f} | {ood['baseline']['hidden_rmse_m']:.4f} | {ood['fixed_lag']['hidden_rmse_m']:.4f} |",
        "",
        "## Boundary",
        "",
        "The smoother deliberately incurs the reported lag and is evaluated offline. It is not represented as a zero-latency live estimator. The classical causal filter remains available and is the comparison baseline.",
        "",
    ]
    (out_dir / "GHOST_X_G11_FIXED_LAG.md").write_text("\n".join(lines), encoding="utf-8")


def _rmse(values: list[float]) -> float:
    return float(math.sqrt(statistics.fmean(values))) if values else float("inf")


def _percentile(values: list[float], percentile: float) -> float:
    return float(np.percentile(np.sqrt(np.asarray(values, dtype=float)), percentile)) if values else float("inf")
