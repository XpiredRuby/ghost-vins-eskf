"""Deterministic controlled-truth campaign for GHOST-X Phase G4.

The campaign creates one canonical truth/measurement stream per trial, hashes it,
and replays the exact same ordered records through the CV baseline, formal IMM,
and GHOST-MH.  Software truth is time synchronized and carries a declared
uncertainty; it is not a substitute for the later physical ground-truth campaign.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.stats import wilcoxon

from analysis.ghost_x_offline_estimators import make_default_adapters

SCENARIO_FAMILIES = (
    "stationary",
    "constant_velocity",
    "acceleration_deceleration",
    "coordinated_arc",
    "stop_and_go",
    "abrupt_maneuver",
    "complete_occlusion",
    "repeated_reentry",
)
ESTIMATORS = ("cv_kalman", "formal_imm", "ghost_mh")
CLAIM_BOUNDARY = (
    "Deterministic software controlled-truth evidence only. It supports algorithmic regression and paired "
    "comparison under declared synthetic assumptions; it does not establish physical tracking accuracy, "
    "real-flight performance, or universal estimator superiority."
)


@dataclass(frozen=True)
class CampaignConfig:
    seed: int = 260713
    repeats_per_family: int = 3
    dt_s: float = 0.1
    duration_s: float = 16.0
    measurement_covariance_xy: tuple[tuple[float, float], tuple[float, float]] = (
        (4.0e-4, 5.0e-5),
        (5.0e-5, 2.5e-4),
    )
    truth_position_variance_m2: float = 1.0e-8
    truth_velocity_variance_m2ps2: float = 1.0e-8
    bootstrap_samples: int = 2000

    @property
    def trial_count(self) -> int:
        return len(SCENARIO_FAMILIES) * self.repeats_per_family

    def validate(self) -> None:
        if self.repeats_per_family < 3:
            raise ValueError("repeats_per_family must be at least 3")
        if self.dt_s <= 0.0 or self.duration_s <= 2.0 * self.dt_s:
            raise ValueError("invalid dt_s or duration_s")
        r = np.asarray(self.measurement_covariance_xy, dtype=float)
        if r.shape != (2, 2) or not np.allclose(r, r.T) or np.min(np.linalg.eigvalsh(r)) <= 0.0:
            raise ValueError("measurement covariance must be symmetric positive definite")
        if self.truth_position_variance_m2 <= 0.0 or self.truth_velocity_variance_m2ps2 <= 0.0:
            raise ValueError("truth uncertainty must be positive")
        if self.bootstrap_samples < 200:
            raise ValueError("bootstrap_samples must be at least 200")

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "repeats_per_family": self.repeats_per_family,
            "dt_s": self.dt_s,
            "duration_s": self.duration_s,
            "measurement_covariance_xy": [list(row) for row in self.measurement_covariance_xy],
            "truth_position_variance_m2": self.truth_position_variance_m2,
            "truth_velocity_variance_m2ps2": self.truth_velocity_variance_m2ps2,
            "bootstrap_samples": self.bootstrap_samples,
        }


def load_config(path: Path) -> CampaignConfig:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("G4 config root must be a mapping")
    campaign = data.get("campaign", data)
    covariance = campaign.get("measurement_covariance_xy", [[4.0e-4, 5.0e-5], [5.0e-5, 2.5e-4]])
    cfg = CampaignConfig(
        seed=int(campaign.get("seed", 260713)),
        repeats_per_family=int(campaign.get("repeats_per_family", 3)),
        dt_s=float(campaign.get("dt_s", 0.1)),
        duration_s=float(campaign.get("duration_s", 16.0)),
        measurement_covariance_xy=tuple(tuple(float(v) for v in row) for row in covariance),
        truth_position_variance_m2=float(campaign.get("truth_position_variance_m2", 1.0e-8)),
        truth_velocity_variance_m2ps2=float(campaign.get("truth_velocity_variance_m2ps2", 1.0e-8)),
        bootstrap_samples=int(campaign.get("bootstrap_samples", 2000)),
    )
    cfg.validate()
    return cfg


def generate_canonical_trial(family: str, repeat: int, config: CampaignConfig) -> list[dict[str, Any]]:
    if family not in SCENARIO_FAMILIES:
        raise ValueError(f"unsupported family: {family}")
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    seed = _trial_seed(config.seed, family, repeat)
    rng = np.random.default_rng(seed)
    r = np.asarray(config.measurement_covariance_xy, dtype=float)
    times = np.arange(0.0, config.duration_s + 0.5 * config.dt_s, config.dt_s)
    rows: list[dict[str, Any]] = []
    for index, t_s in enumerate(times):
        state = truth_state(family, float(t_s), repeat, config.duration_s)
        visible = visibility(family, float(t_s), config.duration_s)
        measurement = None
        if visible:
            noise = rng.multivariate_normal(np.zeros(2), r)
            measurement = [float(state[0] + noise[0]), float(state[1] + noise[1])]
        rows.append(
            {
                "sequence": index,
                "t_s": round(float(t_s), 9),
                "dt_s": config.dt_s,
                "scenario_family": family,
                "repeat": repeat,
                "visible": visible,
                "truth": {
                    "x_m": float(state[0]),
                    "y_m": float(state[1]),
                    "vx_mps": float(state[2]),
                    "vy_mps": float(state[3]),
                    "covariance_diag": [
                        config.truth_position_variance_m2,
                        config.truth_position_variance_m2,
                        config.truth_velocity_variance_m2ps2,
                        config.truth_velocity_variance_m2ps2,
                    ],
                    "source": "DETERMINISTIC_ANALYTIC_SOFTWARE_TRUTH",
                },
                "measurement_xy_m": measurement,
                "measurement_covariance_xy_m2": [list(row) for row in config.measurement_covariance_xy],
                "measurement_seed": seed,
            }
        )
    return rows


def truth_state(family: str, t: float, repeat: int, duration_s: float) -> tuple[float, float, float, float]:
    scale = 1.0 + 0.05 * (repeat - 2)
    if family == "stationary":
        return (1.0 + 0.05 * repeat, -0.15 + 0.03 * repeat, 0.0, 0.0)
    if family in {"constant_velocity", "complete_occlusion", "repeated_reentry"}:
        vx, vy = 0.20 * scale, 0.055 * scale
        return (0.60 + vx * t, -0.35 + vy * t, vx, vy)
    if family == "acceleration_deceleration":
        x0, y0 = 0.5, -0.2
        if t < 5.0:
            ax = 0.045 * scale
            vx = 0.10 + ax * t
            x = x0 + 0.10 * t + 0.5 * ax * t * t
        elif t < 11.0:
            ax1 = 0.045 * scale
            v5 = 0.10 + ax1 * 5.0
            x5 = x0 + 0.10 * 5.0 + 0.5 * ax1 * 25.0
            ax = -0.035 * scale
            tau = t - 5.0
            vx = v5 + ax * tau
            x = x5 + v5 * tau + 0.5 * ax * tau * tau
        else:
            ax1 = 0.045 * scale
            v5 = 0.10 + ax1 * 5.0
            x5 = x0 + 0.10 * 5.0 + 0.5 * ax1 * 25.0
            ax2 = -0.035 * scale
            v11 = v5 + ax2 * 6.0
            x11 = x5 + v5 * 6.0 + 0.5 * ax2 * 36.0
            vx = v11
            x = x11 + v11 * (t - 11.0)
        vy = 0.025 * math.sin(0.4 * t)
        y = y0 + 0.0625 * (1.0 - math.cos(0.4 * t))
        return (x, y, vx, vy)
    if family == "coordinated_arc":
        radius = 1.15 + 0.05 * repeat
        omega = 0.22 * scale
        theta = -0.7 + omega * t
        x = 1.6 + radius * math.cos(theta)
        y = -0.3 + radius * math.sin(theta)
        return (x, y, -radius * omega * math.sin(theta), radius * omega * math.cos(theta))
    if family == "stop_and_go":
        vx = 0.22 * scale
        if t < 4.5:
            return (0.5 + vx * t, -0.15, vx, 0.0)
        x_stop = 0.5 + vx * 4.5
        if t < 9.0:
            return (x_stop, -0.15, 0.0, 0.0)
        return (x_stop + vx * (t - 9.0), -0.15 + 0.03 * (t - 9.0), vx, 0.03)
    if family == "abrupt_maneuver":
        v1 = np.array([0.20 * scale, 0.02], dtype=float)
        v2 = np.array([-0.04, 0.25 * scale], dtype=float)
        switch = 7.0 + 0.2 * (repeat - 2)
        start = np.array([0.7, -0.5], dtype=float)
        if t <= switch:
            p = start + v1 * t
            return (float(p[0]), float(p[1]), float(v1[0]), float(v1[1]))
        pivot = start + v1 * switch
        p = pivot + v2 * (t - switch)
        return (float(p[0]), float(p[1]), float(v2[0]), float(v2[1]))
    raise ValueError(f"unknown family: {family}")


def visibility(family: str, t: float, duration_s: float) -> bool:
    if family == "complete_occlusion":
        return not (5.0 <= t < 10.0)
    if family == "repeated_reentry":
        return not ((3.5 <= t < 5.0) or (7.0 <= t < 9.2) or (12.0 <= t < 13.0))
    if family == "abrupt_maneuver":
        return not (6.4 <= t < 8.8)
    if family == "coordinated_arc":
        return not (8.0 <= t < 10.0)
    return True


def run_trial(rows: list[dict[str, Any]], estimator_options: dict[str, Any] | None = None) -> dict[str, Any]:
    if not rows:
        raise ValueError("canonical stream cannot be empty")
    options = estimator_options or {}
    dt = float(rows[0]["dt_s"])
    r = rows[0]["measurement_covariance_xy_m2"]
    adapters = make_default_adapters(
        dt,
        r,
        imm_smooth_acceleration_std_mps2=float(options.get("imm_smooth_acceleration_std_mps2", 0.015)),
        imm_maneuver_acceleration_std_mps2=float(options.get("imm_maneuver_acceleration_std_mps2", 0.75)),
        mh_accel_temperature=float(options.get("mh_accel_temperature", 0.30)),
        mh_max_occlusion_s=float(options.get("mh_max_occlusion_s", 20.0)),
    )
    outputs: dict[str, list[dict[str, Any]]] = {name: [] for name in ESTIMATORS}
    previous_visible = bool(rows[0]["visible"])
    reacquisition_starts: list[float] = []
    for row in rows:
        measurement = row["measurement_xy_m"]
        visible = bool(row["visible"])
        if visible and not previous_visible:
            reacquisition_starts.append(float(row["t_s"]))
        previous_visible = visible
        for name, adapter in adapters.items():
            estimate = adapter.step(float(row["dt_s"]), measurement)
            outputs[name].append(
                {
                    "sequence": row["sequence"],
                    "t_s": row["t_s"],
                    "visible": visible,
                    "measurement_present": measurement is not None,
                    **estimate.to_dict(),
                }
            )
    metrics = {
        name: compute_metrics(rows, estimator_rows, reacquisition_starts)
        for name, estimator_rows in outputs.items()
    }
    return {"outputs": outputs, "metrics": metrics}


def compute_metrics(
    canonical: list[dict[str, Any]], outputs: list[dict[str, Any]], reacquisition_starts: list[float]
) -> dict[str, Any]:
    position_sq: list[float] = []
    velocity_sq: list[float] = []
    hidden_sq: list[float] = []
    covariance_traces: list[float] = []
    hidden_covariance_traces: list[float] = []
    reset_count = 0
    initialized_count = 0
    by_time = {float(row["t_s"]): row for row in outputs}
    for truth_row, output in zip(canonical, outputs):
        reset_count += int(bool(output.get("reset")))
        state = output.get("state")
        if not output.get("initialized") or not isinstance(state, dict):
            continue
        initialized_count += 1
        truth = truth_row["truth"]
        p_error = (float(state["x_m"]) - float(truth["x_m"])) ** 2 + (
            float(state["y_m"]) - float(truth["y_m"])
        ) ** 2
        v_error = (float(state["vx_mps"]) - float(truth["vx_mps"])) ** 2 + (
            float(state["vy_mps"]) - float(truth["vy_mps"])
        ) ** 2
        position_sq.append(p_error)
        velocity_sq.append(v_error)
        if not truth_row["visible"]:
            hidden_sq.append(p_error)
        covariance = output.get("covariance")
        if isinstance(covariance, list) and len(covariance) >= 2:
            trace = float(covariance[0][0]) + float(covariance[1][1])
            covariance_traces.append(trace)
            if not truth_row["visible"]:
                hidden_covariance_traces.append(trace)

    endpoint_error = None
    for truth_row, output in zip(reversed(canonical), reversed(outputs)):
        state = output.get("state")
        if output.get("initialized") and isinstance(state, dict):
            endpoint_error = math.hypot(
                float(state["x_m"]) - float(truth_row["truth"]["x_m"]),
                float(state["y_m"]) - float(truth_row["truth"]["y_m"]),
            )
            break

    reacquisition_latencies: list[float] = []
    for start in reacquisition_starts:
        candidates = [
            row
            for t_s, row in sorted(by_time.items())
            if t_s >= start - 1e-9 and row.get("initialized") and row.get("measurement_present")
        ]
        if candidates:
            reacquisition_latencies.append(max(0.0, float(candidates[0]["t_s"]) - start))

    first_cov = covariance_traces[0] if covariance_traces else None
    max_hidden_cov = max(hidden_covariance_traces) if hidden_covariance_traces else None
    return {
        "position_rmse_m": _rmse(position_sq),
        "velocity_rmse_mps": _rmse(velocity_sq),
        "hidden_position_rmse_m": _rmse(hidden_sq),
        "endpoint_error_m": endpoint_error,
        "mean_position_covariance_trace_m2": statistics.fmean(covariance_traces) if covariance_traces else None,
        "max_position_covariance_trace_m2": max(covariance_traces) if covariance_traces else None,
        "max_hidden_position_covariance_trace_m2": max_hidden_cov,
        "hidden_covariance_growth_ratio": (
            max_hidden_cov / first_cov if max_hidden_cov is not None and first_cov and first_cov > 0.0 else None
        ),
        "reacquisition_time_s": max(reacquisition_latencies) if reacquisition_latencies else 0.0,
        "reset_count": reset_count,
        "initialized_fraction": initialized_count / len(outputs),
        "failed": initialized_count == 0,
        "failure_reason": "NO_INITIALIZED_OUTPUT" if initialized_count == 0 else None,
    }


def run_campaign(
    config: CampaignConfig,
    out_dir: Path,
    *,
    code_provenance: dict[str, Any] | None = None,
    estimator_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config.validate()
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "canonical_streams"
    result_dir = out_dir / "estimator_outputs"
    trial_dir = out_dir / "trial_metrics"
    for path in (raw_dir, result_dir, trial_dir):
        path.mkdir(exist_ok=True)

    blind_map = _blinded_labels(config.seed)
    trials: list[dict[str, Any]] = []
    raw_hashes: dict[str, str] = {}
    for family in SCENARIO_FAMILIES:
        for repeat in range(1, config.repeats_per_family + 1):
            trial_id = f"g4_{family}_rep{repeat:02d}"
            try:
                canonical = generate_canonical_trial(family, repeat, config)
                raw_path = raw_dir / f"{trial_id}.jsonl"
                _write_jsonl(raw_path, canonical)
                raw_hash = sha256_file(raw_path)
                raw_hashes[trial_id] = raw_hash
                result = run_trial(canonical, estimator_options)
                output_hashes: dict[str, str] = {}
                for estimator, rows in result["outputs"].items():
                    path = result_dir / f"{trial_id}__{estimator}.jsonl"
                    _write_jsonl(path, rows)
                    output_hashes[estimator] = sha256_file(path)
                trial_result = {
                    "trial_id": trial_id,
                    "scenario_family": family,
                    "repeat": repeat,
                    "status": "accepted",
                    "canonical_stream_sha256": raw_hash,
                    "estimator_input_sha256": {name: raw_hash for name in ESTIMATORS},
                    "estimator_output_sha256": output_hashes,
                    "metrics": result["metrics"],
                    "failure_reason": None,
                }
            except Exception as exc:  # preserve invalid trials instead of dropping them
                trial_result = {
                    "trial_id": trial_id,
                    "scenario_family": family,
                    "repeat": repeat,
                    "status": "invalid",
                    "canonical_stream_sha256": raw_hashes.get(trial_id),
                    "estimator_input_sha256": {},
                    "estimator_output_sha256": {},
                    "metrics": {},
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                }
            trials.append(trial_result)
            (trial_dir / f"{trial_id}.json").write_text(
                json.dumps(trial_result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    aggregate = aggregate_metrics(trials, config.bootstrap_samples, config.seed)
    public = public_blinded_summary(aggregate, blind_map)
    manifest = {
        "schema_version": 1,
        "phase": "G4_CONTROLLED_TRUTH_CAMPAIGN",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config.to_dict(),
        "scenario_families": list(SCENARIO_FAMILIES),
        "planned_trials": config.trial_count,
        "accepted_trials": sum(row["status"] == "accepted" for row in trials),
        "invalid_trials": sum(row["status"] != "accepted" for row in trials),
        "estimators": list(ESTIMATORS),
        "identical_input_rule": "Each estimator replays the same canonical JSONL stream and hash for a trial.",
        "truth_model": {
            "source": "DETERMINISTIC_ANALYTIC_SOFTWARE_TRUTH",
            "time_synchronized": True,
            "position_variance_m2": config.truth_position_variance_m2,
            "velocity_variance_m2ps2": config.truth_velocity_variance_m2ps2,
        },
        "code_provenance": code_provenance or {},
        "raw_stream_hashes": raw_hashes,
        "claim_boundary": CLAIM_BOUNDARY,
        "trials": trials,
        "aggregate": aggregate,
    }
    (out_dir / "campaign_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "blind_key.private.json").write_text(
        json.dumps({"seed": config.seed, "mapping": blind_map}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "public_blinded_summary.json").write_text(
        json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_trial_csv(trials, out_dir / "trial_metrics.csv")
    (out_dir / "G4_CONTROLLED_TRUTH_REPORT.md").write_text(
        format_markdown(manifest, public), encoding="utf-8"
    )
    return manifest


def aggregate_metrics(trials: list[dict[str, Any]], n_boot: int, seed: int) -> dict[str, Any]:
    accepted = [row for row in trials if row["status"] == "accepted"]
    metrics = (
        "position_rmse_m",
        "velocity_rmse_mps",
        "hidden_position_rmse_m",
        "endpoint_error_m",
        "reacquisition_time_s",
    )
    by_family: dict[str, Any] = {}
    for family in SCENARIO_FAMILIES:
        family_rows = [row for row in accepted if row["scenario_family"] == family]
        by_family[family] = _aggregate_group(family_rows, metrics, n_boot, seed + SCENARIO_FAMILIES.index(family))
    return {
        "overall": _aggregate_group(accepted, metrics, n_boot, seed),
        "by_scenario_family": by_family,
        "failure_counts": {
            name: sum(
                int(bool(row.get("metrics", {}).get(name, {}).get("failed")))
                for row in accepted
            )
            for name in ESTIMATORS
        },
        "invalid_trial_count": len(trials) - len(accepted),
    }


def _aggregate_group(rows: list[dict[str, Any]], metrics: Iterable[str], n_boot: int, seed: int) -> dict[str, Any]:
    estimator_summaries: dict[str, Any] = {}
    for estimator in ESTIMATORS:
        estimator_summaries[estimator] = {}
        for metric in metrics:
            values = [
                float(row["metrics"][estimator][metric])
                for row in rows
                if _finite(row.get("metrics", {}).get(estimator, {}).get(metric))
            ]
            estimator_summaries[estimator][metric] = _distribution_summary(values)
    paired: dict[str, Any] = {}
    pairs = (("formal_imm", "cv_kalman"), ("ghost_mh", "cv_kalman"), ("ghost_mh", "formal_imm"))
    for left, right in pairs:
        key = f"{left}_minus_{right}"
        paired[key] = {}
        for metric in metrics:
            diffs = []
            for row in rows:
                a = row.get("metrics", {}).get(left, {}).get(metric)
                b = row.get("metrics", {}).get(right, {}).get(metric)
                if _finite(a) and _finite(b):
                    diffs.append(float(a) - float(b))
            paired[key][metric] = paired_difference_summary(diffs, n_boot, seed)
    return {"trial_count": len(rows), "estimators": estimator_summaries, "paired": paired}


def paired_difference_summary(differences: list[float], n_boot: int, seed: int) -> dict[str, Any]:
    if not differences:
        return {"n": 0, "median": None, "mean": None, "bootstrap_ci_95": None, "wilcoxon": None}
    rng = random.Random(seed)
    boot = []
    for _ in range(n_boot):
        boot.append(statistics.median(rng.choice(differences) for _ in differences))
    boot.sort()
    lo = boot[max(0, int(0.025 * len(boot)))]
    hi = boot[min(len(boot) - 1, int(0.975 * len(boot)))]
    if all(abs(value) <= 1e-15 for value in differences):
        w = {"statistic": 0.0, "p_value": 1.0, "valid": True}
    elif len(differences) >= 2:
        result = wilcoxon(differences)
        w = {"statistic": float(result.statistic), "p_value": float(result.pvalue), "valid": True}
    else:
        w = {"statistic": None, "p_value": None, "valid": False}
    return {
        "n": len(differences),
        "median": statistics.median(differences),
        "mean": statistics.fmean(differences),
        "bootstrap_ci_95": {"low": lo, "high": hi, "samples": n_boot, "seed": seed},
        "wilcoxon": w,
        "sign_convention": "negative means the left estimator has lower error/time than the right estimator",
    }


def public_blinded_summary(aggregate: dict[str, Any], blind_map: dict[str, str]) -> dict[str, Any]:
    reverse = {name: label for name, label in blind_map.items()}
    overall = aggregate["overall"]
    blinded_estimators = {reverse[name]: value for name, value in overall["estimators"].items()}
    blinded_pairs = {}
    for key, value in overall["paired"].items():
        left, right = key.split("_minus_")
        blinded_pairs[f"{reverse[left]}_minus_{reverse[right]}"] = value
    return {
        "schema_version": 1,
        "labels_blinded": True,
        "estimators": blinded_estimators,
        "paired": blinded_pairs,
        "claim_boundary": CLAIM_BOUNDARY,
        "unblinding_key_location": "blind_key.private.json",
    }


def format_markdown(manifest: dict[str, Any], public: dict[str, Any]) -> str:
    lines = [
        "# GHOST-X G4 Controlled-Truth Campaign",
        "",
        f"- Planned trials: `{manifest['planned_trials']}`",
        f"- Accepted trials: `{manifest['accepted_trials']}`",
        f"- Invalid trials retained: `{manifest['invalid_trials']}`",
        f"- Scenario families: `{len(manifest['scenario_families'])}`",
        "- Identical inputs: canonical per-trial stream hash is recorded for all estimators",
        "- Full software truth: position, velocity, timestamp and declared truth covariance",
        "",
        f"> {manifest['claim_boundary']}",
        "",
        "## Blinded aggregate position RMSE",
        "",
        "| Label | n | median (m) | mean (m) | 95th percentile (m) |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, summary in public["estimators"].items():
        row = summary["position_rmse_m"]
        lines.append(
            f"| `{label}` | {row['n']} | {_fmt(row['median'])} | {_fmt(row['mean'])} | {_fmt(row['p95'])} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Estimator identities are deliberately separated into `blind_key.private.json`. Paired bootstrap and Wilcoxon results are machine-readable in the manifest. Statistical significance is not interpreted as universal superiority.",
            "",
        ]
    )
    return "\n".join(lines)


def write_trial_csv(trials: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "trial_id",
        "scenario_family",
        "repeat",
        "status",
        "canonical_stream_sha256",
        "estimator",
        "position_rmse_m",
        "velocity_rmse_mps",
        "hidden_position_rmse_m",
        "endpoint_error_m",
        "reacquisition_time_s",
        "reset_count",
        "failure_reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for trial in trials:
            if trial["status"] != "accepted":
                writer.writerow(
                    {
                        "trial_id": trial["trial_id"],
                        "scenario_family": trial["scenario_family"],
                        "repeat": trial["repeat"],
                        "status": trial["status"],
                        "canonical_stream_sha256": trial.get("canonical_stream_sha256"),
                        "failure_reason": trial.get("failure_reason"),
                    }
                )
                continue
            for estimator in ESTIMATORS:
                metric = trial["metrics"][estimator]
                writer.writerow(
                    {
                        "trial_id": trial["trial_id"],
                        "scenario_family": trial["scenario_family"],
                        "repeat": trial["repeat"],
                        "status": trial["status"],
                        "canonical_stream_sha256": trial["canonical_stream_sha256"],
                        "estimator": estimator,
                        **{key: metric.get(key) for key in fields if key in metric},
                    }
                )


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "std": None, "p95": None}
    ordered = sorted(values)
    index = int(round(0.95 * (len(ordered) - 1)))
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "p95": ordered[index],
    }


def _blinded_labels(seed: int) -> dict[str, str]:
    names = list(ESTIMATORS)
    labels = ["Estimator A", "Estimator B", "Estimator C"]
    random.Random(seed ^ 0xB11D).shuffle(labels)
    return dict(zip(names, labels))


def _trial_seed(seed: int, family: str, repeat: int) -> int:
    digest = hashlib.sha256(f"{seed}:{family}:{repeat}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFF


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _rmse(squared_errors: list[float]) -> float | None:
    return math.sqrt(statistics.fmean(squared_errors)) if squared_errors else None


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _fmt(value: Any) -> str:
    return "NA" if not _finite(value) else f"{float(value):.6f}"
