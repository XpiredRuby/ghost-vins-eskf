"""Deterministic software-in-the-loop GNC harness for Project GHOST.

This module closes a software-only loop:

synthetic target truth -> noisy/intermittent measurements -> formal IMM estimate
-> bounded relative-standoff guidance -> acceleration-limited velocity control
-> first-order follower plant.

It is evidence of software integration and closed-loop behavior only. It is not
PX4, flight, hardware-in-the-loop, or vehicle-safety validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

import numpy as np

SOFTWARE_IN_THE_LOOP_ONLY = "SOFTWARE_IN_THE_LOOP_ONLY"
NO_FLIGHT_OR_HARDWARE_CONTROL_CLAIM = "NO_FLIGHT_OR_HARDWARE_CONTROL_CLAIM"
TRACKING = "TRACKING"
PREDICTION = "PREDICTION"
SAFE_HOLD = "SAFE_HOLD"


class Estimator(Protocol):
    def step(self, measurement: Iterable[float] | None) -> Any: ...


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    duration_s: float = 18.0
    dt_s: float = 0.05
    seed: int = 260710
    measurement_std_m: float = 0.02
    dropout_windows_s: tuple[tuple[float, float], ...] = ()
    prediction_horizon_s: float = 2.0
    standoff_m: float = 1.5
    approach_gain_per_s: float = 0.75
    max_approach_speed_mps: float = 1.0
    max_desired_speed_mps: float = 1.8
    velocity_kp_per_s: float = 2.2
    max_acceleration_mps2: float = 2.5
    actuator_time_constant_s: float = 0.18
    follower_drag_per_s: float = 0.05
    target_initial_position_m: tuple[float, float] = (5.0, 0.0)
    target_initial_velocity_mps: tuple[float, float] = (0.35, 0.05)
    follower_initial_position_m: tuple[float, float] = (0.0, -1.5)
    follower_initial_velocity_mps: tuple[float, float] = (0.65, 0.0)


@dataclass(frozen=True)
class ScenarioSummary:
    scenario: str
    duration_s: float
    steps: int
    final_standoff_error_m: float
    rms_standoff_error_after_5s_m: float
    max_estimation_error_m: float
    visible_estimation_rmse_m: float
    max_measurement_age_s: float
    safe_hold_time_s: float
    reacquisition_count: int
    max_command_acceleration_mps2: float
    max_achieved_acceleration_mps2: float
    max_follower_speed_mps: float
    minimum_separation_m: float
    command_saturation_fraction: float
    finite_output: bool
    integration_status: str = SOFTWARE_IN_THE_LOOP_ONLY
    claims_boundary: str = NO_FLIGHT_OR_HARDWARE_CONTROL_CLAIM


@dataclass(frozen=True)
class ScenarioResult:
    config: ScenarioConfig
    summary: ScenarioSummary
    samples: list[dict[str, Any]] = field(repr=False)

    def to_dict(self, include_samples: bool = True) -> dict[str, Any]:
        out = {"config": asdict(self.config), "summary": asdict(self.summary)}
        if include_samples:
            out["samples"] = self.samples
        return out


def default_scenarios() -> tuple[ScenarioConfig, ...]:
    return (
        ScenarioConfig(name="nominal_visible"),
        ScenarioConfig(name="short_dropout", dropout_windows_s=((6.0, 7.5),)),
        ScenarioConfig(name="long_dropout_safe_hold", dropout_windows_s=((6.0, 10.0),)),
    )


def run_scenario(
    config: ScenarioConfig,
    estimator_factory: Callable[[ScenarioConfig], Estimator] | None = None,
) -> ScenarioResult:
    _validate_config(config)
    rng = np.random.default_rng(config.seed)
    estimator = (estimator_factory or _default_estimator_factory)(config)

    target_p = np.asarray(config.target_initial_position_m, dtype=float)
    target_v = np.asarray(config.target_initial_velocity_mps, dtype=float)
    follower_p = np.asarray(config.follower_initial_position_m, dtype=float)
    follower_v = np.asarray(config.follower_initial_velocity_mps, dtype=float)
    achieved_a = np.zeros(2, dtype=float)

    measurement_age_s = 0.0
    prior_supervisor = TRACKING
    reacquisition_count = 0
    samples: list[dict[str, Any]] = []

    standoff_errors_after_5s: list[float] = []
    visible_estimation_errors: list[float] = []
    all_estimation_errors: list[float] = []
    command_norms: list[float] = []
    achieved_norms: list[float] = []
    follower_speeds: list[float] = []
    separations: list[float] = []
    safe_hold_steps = 0
    saturated_steps = 0

    steps = int(round(config.duration_s / config.dt_s))
    for k in range(steps):
        t_s = (k + 1) * config.dt_s

        target_a = target_acceleration(t_s)
        target_v = target_v + target_a * config.dt_s
        target_p = target_p + target_v * config.dt_s

        visible = not _in_any_window(t_s, config.dropout_windows_s)
        if visible:
            measurement = target_p + rng.normal(0.0, config.measurement_std_m, size=2)
            measurement_age_s = 0.0
        else:
            measurement = None
            measurement_age_s += config.dt_s

        estimator_step = estimator.step(measurement)
        est_x, mode_probabilities = _extract_estimator_state(estimator_step)
        estimate_p = est_x[:2]
        estimate_v = est_x[2:4]

        if visible:
            supervisor = TRACKING
        elif measurement_age_s <= config.prediction_horizon_s + 1e-12:
            supervisor = PREDICTION
        else:
            supervisor = SAFE_HOLD
            safe_hold_steps += 1

        if supervisor == TRACKING and prior_supervisor in {PREDICTION, SAFE_HOLD}:
            reacquisition_count += 1

        desired_v = guidance_velocity(
            estimate_p=estimate_p,
            estimate_v=estimate_v,
            follower_p=follower_p,
            supervisor=supervisor,
            standoff_m=config.standoff_m,
            approach_gain_per_s=config.approach_gain_per_s,
            max_approach_speed_mps=config.max_approach_speed_mps,
            max_desired_speed_mps=config.max_desired_speed_mps,
        )
        raw_command = config.velocity_kp_per_s * (desired_v - follower_v)
        command_a = _limit_norm(raw_command, config.max_acceleration_mps2)
        if np.linalg.norm(raw_command) > config.max_acceleration_mps2 + 1e-12:
            saturated_steps += 1

        alpha = min(1.0, config.dt_s / config.actuator_time_constant_s)
        achieved_a = achieved_a + alpha * (command_a - achieved_a)
        follower_v = follower_v + (
            achieved_a - config.follower_drag_per_s * follower_v
        ) * config.dt_s
        follower_p = follower_p + follower_v * config.dt_s

        separation = float(np.linalg.norm(target_p - follower_p))
        standoff_error = abs(separation - config.standoff_m)
        estimation_error = float(np.linalg.norm(estimate_p - target_p))

        if t_s >= 5.0:
            standoff_errors_after_5s.append(standoff_error)
        if visible:
            visible_estimation_errors.append(estimation_error)
        all_estimation_errors.append(estimation_error)
        command_norms.append(float(np.linalg.norm(command_a)))
        achieved_norms.append(float(np.linalg.norm(achieved_a)))
        follower_speeds.append(float(np.linalg.norm(follower_v)))
        separations.append(separation)

        samples.append(
            {
                "t_s": float(t_s),
                "visible": bool(visible),
                "supervisor": supervisor,
                "measurement_age_s": float(measurement_age_s),
                "target": {
                    "x_m": float(target_p[0]),
                    "y_m": float(target_p[1]),
                    "vx_mps": float(target_v[0]),
                    "vy_mps": float(target_v[1]),
                },
                "estimate": {
                    "x_m": float(estimate_p[0]),
                    "y_m": float(estimate_p[1]),
                    "vx_mps": float(estimate_v[0]),
                    "vy_mps": float(estimate_v[1]),
                },
                "follower": {
                    "x_m": float(follower_p[0]),
                    "y_m": float(follower_p[1]),
                    "vx_mps": float(follower_v[0]),
                    "vy_mps": float(follower_v[1]),
                },
                "desired_velocity_mps": [float(v) for v in desired_v],
                "command_acceleration_mps2": [float(v) for v in command_a],
                "achieved_acceleration_mps2": [float(v) for v in achieved_a],
                "separation_m": separation,
                "standoff_error_m": standoff_error,
                "estimation_error_m": estimation_error,
                "mode_probabilities": mode_probabilities,
            }
        )
        prior_supervisor = supervisor

    finite_output = all(
        math.isfinite(value)
        for values in (
            all_estimation_errors,
            command_norms,
            achieved_norms,
            follower_speeds,
            separations,
        )
        for value in values
    )
    summary = ScenarioSummary(
        scenario=config.name,
        duration_s=config.duration_s,
        steps=steps,
        final_standoff_error_m=abs(separations[-1] - config.standoff_m),
        rms_standoff_error_after_5s_m=_rms(standoff_errors_after_5s),
        max_estimation_error_m=max(all_estimation_errors),
        visible_estimation_rmse_m=_rms(visible_estimation_errors),
        max_measurement_age_s=max(sample["measurement_age_s"] for sample in samples),
        safe_hold_time_s=safe_hold_steps * config.dt_s,
        reacquisition_count=reacquisition_count,
        max_command_acceleration_mps2=max(command_norms),
        max_achieved_acceleration_mps2=max(achieved_norms),
        max_follower_speed_mps=max(follower_speeds),
        minimum_separation_m=min(separations),
        command_saturation_fraction=saturated_steps / steps,
        finite_output=finite_output,
    )
    return ScenarioResult(config=config, summary=summary, samples=samples)


def guidance_velocity(
    *,
    estimate_p: np.ndarray,
    estimate_v: np.ndarray,
    follower_p: np.ndarray,
    supervisor: str,
    standoff_m: float,
    approach_gain_per_s: float,
    max_approach_speed_mps: float,
    max_desired_speed_mps: float,
) -> np.ndarray:
    """Return a bounded desired follower velocity.

    TRACKING/PREDICTION:
      v_des = v_target_est + clip(k_r * (range - standoff)) * LOS_unit

    SAFE_HOLD:
      v_des = 0

    This is a relative-standoff guidance law, not proportional navigation.
    """

    if supervisor == SAFE_HOLD:
        return np.zeros(2, dtype=float)
    if supervisor not in {TRACKING, PREDICTION}:
        raise ValueError(f"unknown supervisor state: {supervisor}")

    relative = np.asarray(estimate_p, dtype=float) - np.asarray(follower_p, dtype=float)
    range_m = float(np.linalg.norm(relative))
    if range_m <= 1e-12:
        line_of_sight = np.zeros(2, dtype=float)
    else:
        line_of_sight = relative / range_m

    approach_speed = float(
        np.clip(
            approach_gain_per_s * (range_m - standoff_m),
            -max_approach_speed_mps,
            max_approach_speed_mps,
        )
    )
    desired = np.asarray(estimate_v, dtype=float) + approach_speed * line_of_sight
    return _limit_norm(desired, max_desired_speed_mps)


def target_acceleration(t_s: float) -> np.ndarray:
    """Predeclared deterministic target maneuver profile."""

    if 4.0 <= t_s < 6.0:
        return np.array([0.0, 0.18], dtype=float)
    if 10.0 <= t_s < 12.0:
        return np.array([-0.14, -0.05], dtype=float)
    return np.zeros(2, dtype=float)


def run_default_suite(out_dir: Path | None = None) -> dict[str, Any]:
    results = [run_scenario(config) for config in default_scenarios()]
    suite = {
        "integration_status": SOFTWARE_IN_THE_LOOP_ONLY,
        "claims_boundary": NO_FLIGHT_OR_HARDWARE_CONTROL_CLAIM,
        "scenarios": [result.to_dict(include_samples=False)["summary"] for result in results],
    }
    if out_dir is not None:
        write_suite_outputs(results, out_dir)
    return suite


def write_suite_outputs(results: list[ScenarioResult], out_dir: Path) -> None:
    out_dir = out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "integration_status": SOFTWARE_IN_THE_LOOP_ONLY,
        "claims_boundary": NO_FLIGHT_OR_HARDWARE_CONTROL_CLAIM,
        "scenarios": [asdict(result.summary) for result in results],
    }
    (out_dir / "closed_loop_gnc_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "closed_loop_gnc_summary.md").write_text(
        _summary_markdown(results),
        encoding="utf-8",
    )

    for result in results:
        path = out_dir / f"{result.config.name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "t_s",
                    "visible",
                    "supervisor",
                    "measurement_age_s",
                    "target_x_m",
                    "target_y_m",
                    "estimate_x_m",
                    "estimate_y_m",
                    "follower_x_m",
                    "follower_y_m",
                    "separation_m",
                    "standoff_error_m",
                    "estimation_error_m",
                    "command_ax_mps2",
                    "command_ay_mps2",
                ]
            )
            for sample in result.samples:
                writer.writerow(
                    [
                        sample["t_s"],
                        sample["visible"],
                        sample["supervisor"],
                        sample["measurement_age_s"],
                        sample["target"]["x_m"],
                        sample["target"]["y_m"],
                        sample["estimate"]["x_m"],
                        sample["estimate"]["y_m"],
                        sample["follower"]["x_m"],
                        sample["follower"]["y_m"],
                        sample["separation_m"],
                        sample["standoff_error_m"],
                        sample["estimation_error_m"],
                        sample["command_acceleration_mps2"][0],
                        sample["command_acceleration_mps2"][1],
                    ]
                )


def _default_estimator_factory(config: ScenarioConfig) -> Estimator:
    from analysis.imm_cycle import make_smooth_maneuver_cv_imm

    initial = (
        config.target_initial_position_m[0],
        config.target_initial_position_m[1],
        config.target_initial_velocity_mps[0],
        config.target_initial_velocity_mps[1],
    )
    return make_smooth_maneuver_cv_imm(
        dt=config.dt_s,
        measurement_std_m=config.measurement_std_m,
        initial_state=initial,
    )


def _extract_estimator_state(step: Any) -> tuple[np.ndarray, dict[str, float]]:
    combined = getattr(step, "combined_estimate", None)
    if combined is None:
        raise TypeError("estimator step must expose combined_estimate")
    state = np.asarray(getattr(combined, "x", None), dtype=float)
    if state.shape != (4,) or not np.isfinite(state).all():
        raise ValueError("estimator combined state must be a finite [x, y, vx, vy] vector")
    probabilities = dict(getattr(step, "mode_probabilities", {}) or {})
    return state, {str(k): float(v) for k, v in probabilities.items()}


def _in_any_window(t_s: float, windows: tuple[tuple[float, float], ...]) -> bool:
    return any(start <= t_s < end for start, end in windows)


def _limit_norm(vector: np.ndarray, limit: float) -> np.ndarray:
    vector = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(vector))
    if norm <= limit or norm <= 1e-12:
        return vector.copy()
    return vector * (limit / norm)


def _rms(values: list[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


def _validate_config(config: ScenarioConfig) -> None:
    positive = {
        "duration_s": config.duration_s,
        "dt_s": config.dt_s,
        "measurement_std_m": config.measurement_std_m,
        "prediction_horizon_s": config.prediction_horizon_s,
        "standoff_m": config.standoff_m,
        "approach_gain_per_s": config.approach_gain_per_s,
        "max_approach_speed_mps": config.max_approach_speed_mps,
        "max_desired_speed_mps": config.max_desired_speed_mps,
        "velocity_kp_per_s": config.velocity_kp_per_s,
        "max_acceleration_mps2": config.max_acceleration_mps2,
        "actuator_time_constant_s": config.actuator_time_constant_s,
    }
    for name, value in positive.items():
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and > 0")
    if config.follower_drag_per_s < 0.0 or not math.isfinite(config.follower_drag_per_s):
        raise ValueError("follower_drag_per_s must be finite and >= 0")
    for start, end in config.dropout_windows_s:
        if not (0.0 <= start < end <= config.duration_s):
            raise ValueError("dropout windows must satisfy 0 <= start < end <= duration")


def _summary_markdown(results: list[ScenarioResult]) -> str:
    lines = [
        "# GHOST Closed-Loop GNC Software-in-the-Loop Summary",
        "",
        f"- Integration status: `{SOFTWARE_IN_THE_LOOP_ONLY}`",
        f"- Claims boundary: `{NO_FLIGHT_OR_HARDWARE_CONTROL_CLAIM}`",
        "",
        "| Scenario | Final standoff error (m) | RMS standoff error after 5 s (m) | Max measurement age (s) | Safe-hold time (s) | Reacquisitions |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        s = result.summary
        lines.append(
            f"| `{s.scenario}` | {s.final_standoff_error_m:.4f} | "
            f"{s.rms_standoff_error_after_5s_m:.4f} | {s.max_measurement_age_s:.3f} | "
            f"{s.safe_hold_time_s:.3f} | {s.reacquisition_count} |"
        )
    lines.extend(
        [
            "",
            "This report is deterministic software-in-the-loop evidence. It is not PX4, hardware-in-the-loop, flight, or vehicle-safety validation.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run GHOST closed-loop GNC software-in-the-loop scenarios.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    suite = run_default_suite(args.out)
    print(json.dumps(suite, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
