#!/usr/bin/env python3
"""
GHOST software-regime offline validation.

No Pi. No camera. No ROS runtime.

This is a candidate pre-hardware acceptance harness for the GHOST V1 tracker:
- calibrated vision-only AprilTag tracker
- heuristic hypothesis bank, not formal IMM/MHT
- stationary-lock + stationary-hold behavior
- synthetic known-truth validation

Important: this file is scaffolding, not final report evidence. Synthetic truth is independent
of the estimator, but the thresholds below remain engineering requirements/placeholders until
hardware-calibrated noise statistics are committed into the repo.

Run:
    python ghost_sim_ros2/analysis/ghost_software_regime.py --out ghost_regime_runs/latest
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple
import argparse
import csv
import html
import json
import math
import random
import statistics


@dataclass(frozen=True)
class RegimeConfig:
    """Candidate software-regime parameters.

    Stationary speed thresholds are intentionally labeled as candidate values. They are set to
    the currently discussed empirical range from the stationary-noise session:
    - ~0.065 m/s at a 1.5 s window
    - ~0.09 m/s at a 1.0 s window

    They should be replaced by values loaded from a committed hardware noise-calibration artifact
    before any PASS report is cited as real-world validation.
    """

    dt_s: float = 0.05
    future_horizon_s: float = 1.5
    future_dt_s: float = 0.10

    stationary_window_s: float = 1.5
    stationary_enter_speed_mps: float = 0.065
    stationary_exit_speed_mps: float = 0.090
    stationary_min_samples: int = 5

    max_occlusion_s: float = 3.0
    reset_after_s: float = 4.0
    max_workspace_range_m: float = 5.0

    stationary_locked_prior: float = 0.95
    stationary_locked_brake_prior: float = 0.03
    stationary_locked_cv_prior: float = 0.02

    measurement_alpha: float = 0.80
    velocity_alpha: float = 0.25

    # Acceptance gates: these are explicit V1 engineering requirements, not derived proof.
    # They must be justified in the design report before the generated PASS is used as evidence.
    stationary_false_motion_limit_mps: float = 0.01
    stationary_hold_fraction_min: float = 0.80
    stationary_prior_min: float = 0.90
    stop_wall_top3_limit_m: float = 0.40
    lateral_top3_limit_m: float = 0.60
    visible_rmse_limit_m: float = 0.10
    colored_noise_stationary_hold_fraction_min: float = 0.60

    threshold_status: str = "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"
    threshold_provenance: str = (
        "Stationary gate uses 0.065/0.090 m/s from the discussed empirical stationary-noise range; "
        "scenario pass/fail limits are V1 engineering requirements/placeholders pending formal traceability."
    )


@dataclass(frozen=True)
class Measurement:
    t_s: float
    visible: bool
    x_m: Optional[float] = None
    y_m: Optional[float] = None

    def xy(self) -> Optional[Tuple[float, float]]:
        if not self.visible or self.x_m is None or self.y_m is None:
            return None
        return float(self.x_m), float(self.y_m)


@dataclass
class Hypothesis:
    rank: int
    model: str
    relative_hypothesis_weight: float
    x_m: float
    y_m: float
    vx_mps: float
    vy_mps: float
    cov_xx: float
    cov_xy: float
    cov_yy: float
    path: List[Dict[str, float]] = field(default_factory=list)

    def terminal_xy(self) -> Tuple[float, float]:
        if self.path:
            p = self.path[-1]
            return float(p["x_m"]), float(p["y_m"])
        return self.x_m, self.y_m


@dataclass
class TrackerOutput:
    sequence: int
    t_s: float
    visible: bool
    initialized: bool
    state_label: str
    x_m: Optional[float]
    y_m: Optional[float]
    vx_mps: Optional[float]
    vy_mps: Optional[float]
    stationary_hold_active: bool
    hidden_stationary_hold_active: bool
    stationary_window_speed_mps: Optional[float]
    occlusion_age_s: Optional[float]
    hypotheses: List[Hypothesis]

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "sequence": self.sequence,
            "t_s": self.t_s,
            "visible": self.visible,
            "initialized": self.initialized,
            "state_label": self.state_label,
            "estimate": None if self.x_m is None else {
                "x_m": self.x_m,
                "y_m": self.y_m,
                "vx_mps": self.vx_mps,
                "vy_mps": self.vy_mps,
            },
            "stationary_hold_active": self.stationary_hold_active,
            "hidden_stationary_hold_active": self.hidden_stationary_hold_active,
            "stationary_window_speed_mps": self.stationary_window_speed_mps,
            "occlusion_age_s": self.occlusion_age_s,
            "hypotheses": [
                {
                    "rank": h.rank,
                    "model": h.model,
                    "relative_hypothesis_weight": h.relative_hypothesis_weight,
                    "x_m": h.x_m,
                    "y_m": h.y_m,
                    "vx_mps": h.vx_mps,
                    "vy_mps": h.vy_mps,
                    "cov_xx": h.cov_xx,
                    "cov_xy": h.cov_xy,
                    "cov_yy": h.cov_yy,
                    "path": h.path,
                }
                for h in self.hypotheses
            ],
        }


class StationaryGate:
    """Rolling least-squares velocity classifier with hysteresis."""

    def __init__(self, config: RegimeConfig):
        self.config = config
        self.history: Deque[Tuple[float, float, float]] = deque()
        self.active = False
        self.window_speed_mps = math.inf

    def update(self, t_s: float, x_m: float, y_m: float) -> None:
        self.history.append((float(t_s), float(x_m), float(y_m)))
        keep_after = t_s - max(5.0, 3.0 * self.config.stationary_window_s)
        while self.history and self.history[0][0] < keep_after:
            self.history.popleft()

        speed = self._ls_speed(t_s)
        self.window_speed_mps = speed
        if not math.isfinite(speed):
            return

        if self.active:
            if speed > self.config.stationary_exit_speed_mps:
                self.active = False
        else:
            if speed < self.config.stationary_enter_speed_mps:
                self.active = True

    def _ls_speed(self, t_s: float) -> float:
        window_start = t_s - self.config.stationary_window_s
        points = [p for p in self.history if p[0] >= window_start]
        if len(points) < self.config.stationary_min_samples:
            return math.inf
        span = points[-1][0] - points[0][0]
        if span < 0.5 * self.config.stationary_window_s:
            return math.inf

        t0 = points[0][0]
        ts = [p[0] - t0 for p in points]
        xs = [p[1] for p in points]
        ys = [p[2] for p in points]

        def slope(vals: List[float]) -> float:
            mt = statistics.fmean(ts)
            mv = statistics.fmean(vals)
            den = sum((t - mt) ** 2 for t in ts)
            if den <= 1e-12:
                return 0.0
            return sum((t - mt) * (v - mv) for t, v in zip(ts, vals)) / den

        return math.hypot(slope(xs), slope(ys))


class GhostRegimeTracker:
    """
    GHOST V1 offline tracker.

    Correct claim: calibrated vision-only tracker with heuristic hypotheses.
    Incorrect claim: formal IMM/MHT/ESKF/VINS or perfect hidden tracking.
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        self.config = config or RegimeConfig()
        self.gate = StationaryGate(self.config)
        self.sequence = 0
        self.initialized = False
        self.x = self.y = self.vx = self.vy = 0.0
        self.last_visible_t: Optional[float] = None
        self.last_visible_xy: Optional[Tuple[float, float]] = None

    def step(self, m: Measurement) -> TrackerOutput:
        self.sequence += 1
        xy = m.xy()
        visible = xy is not None

        if visible:
            assert xy is not None
            self._update_visible(m.t_s, xy[0], xy[1])
        elif self.initialized:
            self._coast_hidden(m.t_s)

        hidden_age = None
        if self.initialized and self.last_visible_t is not None and not visible:
            hidden_age = max(0.0, m.t_s - self.last_visible_t)

        hidden_stationary_hold = (
            self.initialized and (not visible) and self.gate.active
            and hidden_age is not None and hidden_age <= self.config.reset_after_s
        )

        if not self.initialized:
            label = "WAITING_FOR_TARGET"
            x = y = vx = vy = None
            hypotheses: List[Hypothesis] = []
        elif visible:
            label = "VISIBLE - MEASUREMENT LOCK"
            x, y, vx, vy = self.x, self.y, self.vx, self.vy
            hypotheses = [self._hyp(1, "measured_state", 1.0, self.x, self.y, self.vx, self.vy, 0.0025, 0.0, 0.0025)]
        elif hidden_stationary_hold:
            label = "HIDDEN - STATIONARY HOLD"
            x, y = self.last_visible_xy or (self.x, self.y)
            vx = vy = 0.0
            hypotheses = self._stationary_hold_hypotheses(x, y, hidden_age or 0.0)
        elif hidden_age is not None and hidden_age > self.config.reset_after_s:
            label = "HIDDEN - RESET REQUIRED"
            x, y, vx, vy = self.x, self.y, 0.0, 0.0
            hypotheses = []
        else:
            label = "OCCLUDED - HYPOTHESIS BANK"
            x, y, vx, vy = self.x, self.y, self.vx, self.vy
            hypotheses = self._dynamic_hypotheses(hidden_age or 0.0)

        speed = self.gate.window_speed_mps if math.isfinite(self.gate.window_speed_mps) else None
        return TrackerOutput(
            sequence=self.sequence,
            t_s=m.t_s,
            visible=visible,
            initialized=self.initialized,
            state_label=label,
            x_m=x,
            y_m=y,
            vx_mps=vx,
            vy_mps=vy,
            stationary_hold_active=self.gate.active,
            hidden_stationary_hold_active=hidden_stationary_hold,
            stationary_window_speed_mps=speed,
            occlusion_age_s=hidden_age,
            hypotheses=hypotheses,
        )

    def _update_visible(self, t_s: float, mx: float, my: float) -> None:
        if not self.initialized:
            self.initialized = True
            self.x, self.y = mx, my
            self.vx = self.vy = 0.0
        else:
            if self.last_visible_t is not None and self.last_visible_xy is not None:
                dt = max(1e-6, t_s - self.last_visible_t)
                raw_vx = (mx - self.last_visible_xy[0]) / dt
                raw_vy = (my - self.last_visible_xy[1]) / dt
                a = self.config.velocity_alpha
                self.vx = (1.0 - a) * self.vx + a * raw_vx
                self.vy = (1.0 - a) * self.vy + a * raw_vy

            a = self.config.measurement_alpha
            self.x = (1.0 - a) * self.x + a * mx
            self.y = (1.0 - a) * self.y + a * my

        self.last_visible_t = t_s
        self.last_visible_xy = (mx, my)
        self.gate.update(t_s, mx, my)

    def _coast_hidden(self, t_s: float) -> None:
        if self.last_visible_t is None:
            return
        age = max(0.0, t_s - self.last_visible_t)
        dt = min(age, self.config.max_occlusion_s)
        if self.gate.active:
            if self.last_visible_xy:
                self.x, self.y = self.last_visible_xy
            self.vx = self.vy = 0.0
            return
        self.x = (self.last_visible_xy[0] if self.last_visible_xy else self.x) + self.vx * dt
        self.y = (self.last_visible_xy[1] if self.last_visible_xy else self.y) + self.vy * dt
        r = math.hypot(self.x, self.y)
        if r > self.config.max_workspace_range_m and r > 1e-9:
            s = self.config.max_workspace_range_m / r
            self.x *= s
            self.y *= s

    def _stationary_hold_hypotheses(self, x: float, y: float, hidden_age_s: float) -> List[Hypothesis]:
        cov = 0.0025 + 0.0015 * max(0.0, hidden_age_s)
        path = self._stationary_path(x, y, cov)
        return [
            self._hyp(1, "stationary_hold", self.config.stationary_locked_prior, x, y, 0.0, 0.0, cov, 0.0, cov, path),
            self._hyp(2, "brake_hover", self.config.stationary_locked_brake_prior, x, y, 0.0, 0.0, cov * 1.3, 0.0, cov * 1.3, path),
            self._hyp(3, "constant_velocity_suppressed", self.config.stationary_locked_cv_prior, x, y, 0.0, 0.0, cov * 1.6, 0.0, cov * 1.6, path),
        ]

    def _dynamic_hypotheses(self, hidden_age_s: float) -> List[Hypothesis]:
        vx, vy = self.vx, self.vy
        speed = math.hypot(vx, vy)
        ux, uy = (vx / speed, vy / speed) if speed > 1e-9 else (1.0, 0.0)
        lx, ly = -uy, ux
        models = [
            ("constant_velocity", 0.38, vx, vy),
            ("brake_hover", 0.18, 0.0, 0.0),
            ("accelerate_forward", 0.14, vx + 0.20 * ux, vy + 0.20 * uy),
            ("lateral_left", 0.10, vx + 0.15 * lx, vy + 0.15 * ly),
            ("lateral_right", 0.10, vx - 0.15 * lx, vy - 0.15 * ly),
            ("turn_left", 0.05, 0.85 * vx + 0.10 * lx, 0.85 * vy + 0.10 * ly),
            ("turn_right", 0.05, 0.85 * vx - 0.10 * lx, 0.85 * vy - 0.10 * ly),
        ]
        cov = 0.004 + 0.004 * max(0.0, hidden_age_s)
        out = []
        for i, (name, prob, mvx, mvy) in enumerate(models, start=1):
            out.append(self._hyp(i, name, prob, self.x, self.y, mvx, mvy, cov, 0.0, cov, self._linear_path(self.x, self.y, mvx, mvy)))
        return out

    def _linear_path(self, x: float, y: float, vx: float, vy: float) -> List[Dict[str, float]]:
        n = int(round(self.config.future_horizon_s / self.config.future_dt_s))
        return [{"dt_s": k * self.config.future_dt_s, "x_m": x + vx * k * self.config.future_dt_s, "y_m": y + vy * k * self.config.future_dt_s} for k in range(n + 1)]

    def _stationary_path(self, x: float, y: float, cov: float) -> List[Dict[str, float]]:
        n = int(round(self.config.future_horizon_s / self.config.future_dt_s))
        sigma = math.sqrt(max(0.0, cov))
        return [{"dt_s": k * self.config.future_dt_s, "x_m": x, "y_m": y, "uncertainty_sigma_m": sigma + 0.002 * k * self.config.future_dt_s} for k in range(n + 1)]

    @staticmethod
    def _hyp(rank: int, model: str, relative_hypothesis_weight: float, x: float, y: float, vx: float, vy: float, cov_xx: float, cov_xy: float, cov_yy: float, path: Optional[List[Dict[str, float]]] = None) -> Hypothesis:
        return Hypothesis(rank, model, relative_hypothesis_weight, x, y, vx, vy, cov_xx, cov_xy, cov_yy, path or [])


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    duration_s: float
    occlusion_start_s: float
    occlusion_end_s: float
    truth_fn: Callable[[float], Tuple[float, float]]
    visible_fn: Callable[[float], bool]
    noise_profile: str = "white"
    inject_single_outlier: bool = False


@dataclass
class ScenarioMetrics:
    scenario: str
    pass_fail: str
    samples: int
    hidden_samples: int
    rmse_m: float
    p95_error_m: float
    top1_terminal_error_m: float
    top3_best_terminal_error_m: float
    top1_model_at_first_hidden: str
    top1_relative_hypothesis_weight_at_first_hidden: float
    stationary_false_motion_mps: float
    stationary_hold_fraction_hidden: float
    reset_count: int
    threshold_status: str
    threshold_provenance: str
    notes: str


def make_scenarios() -> Dict[str, Scenario]:
    def stationary(t: float) -> Tuple[float, float]:
        return 0.50, 0.00

    def cv(t: float) -> Tuple[float, float]:
        return 0.20 + 0.25 * t, -0.10

    def stop_wall(t: float) -> Tuple[float, float]:
        return 0.20 + 0.30 * min(t, 1.8), 0.05

    def lateral(t: float) -> Tuple[float, float]:
        if t < 2.0:
            return 0.25 + 0.20 * t, 0.0
        if t < 4.0:
            return 0.65, 0.25 * (t - 2.0)
        return 0.65, 0.50

    def long_hidden(t: float) -> Tuple[float, float]:
        return 0.40, 0.10

    def mild_sine(t: float) -> Tuple[float, float]:
        return 0.45 + 0.05 * math.sin(1.5 * t), 0.0

    def hidden(start: float, end: float) -> Callable[[float], bool]:
        return lambda t: not (start <= t <= end)

    return {
        "stationary_hide_reveal": Scenario("stationary_hide_reveal", "stationary before/during/after occlusion", 5.0, 2.0, 4.0, stationary, hidden(2.0, 4.0)),
        "stationary_colored_noise_hide_reveal": Scenario("stationary_colored_noise_hide_reveal", "stationary occlusion with synthetic autocorrelated drift", 5.0, 2.0, 4.0, stationary, hidden(2.0, 4.0), noise_profile="colored_ar1"),
        "constant_velocity_hide_reveal": Scenario("constant_velocity_hide_reveal", "constant velocity through occlusion", 5.0, 2.0, 4.0, cv, hidden(2.0, 4.0)),
        "move_then_stop_behind_wall": Scenario("move_then_stop_behind_wall", "moves, then stops near occlusion", 5.0, 1.8, 4.0, stop_wall, hidden(1.8, 4.0)),
        "lateral_hidden_motion": Scenario("lateral_hidden_motion", "turns laterally while hidden", 5.0, 2.0, 4.0, lateral, hidden(2.0, 4.0)),
        "long_occlusion_reset": Scenario("long_occlusion_reset", "hidden longer than V1 should confidently predict", 7.0, 1.8, 6.5, long_hidden, hidden(1.8, 6.5)),
        "single_outlier_white_noise": Scenario("single_outlier_white_noise", "white Gaussian noise plus one deterministic measurement outlier", 5.0, 99.0, 99.0, mild_sine, lambda t: True, noise_profile="white", inject_single_outlier=True),
    }


def _noise_sample(rng: random.Random, profile: str, drift: Tuple[float, float]) -> Tuple[float, float, Tuple[float, float]]:
    if profile == "colored_ar1":
        # Synthetic AR(1) drift only. This is not yet the committed hardware Allan/PSD replay.
        rho = 0.985
        process_std = 0.0012
        white_std = 0.0025
        dx = rho * drift[0] + rng.gauss(0.0, process_std)
        dy = rho * drift[1] + rng.gauss(0.0, process_std)
        return dx + rng.gauss(0.0, white_std), dy + rng.gauss(0.0, white_std), (dx, dy)
    white_std = 0.004
    return rng.gauss(0.0, white_std), rng.gauss(0.0, white_std), drift


def generate_measurements(scenario: Scenario, config: RegimeConfig, noise_std_m: Optional[float] = None, seed: int = 42) -> List[Measurement]:
    rng = random.Random(seed)
    out: List[Measurement] = []
    drift = (0.0, 0.0)
    n = int(round(scenario.duration_s / config.dt_s))
    for k in range(n + 1):
        t = round(k * config.dt_s, 10)
        visible = scenario.visible_fn(t)
        x, y = scenario.truth_fn(t)
        if visible:
            if noise_std_m is not None and scenario.noise_profile == "white":
                nx, ny = rng.gauss(0.0, noise_std_m), rng.gauss(0.0, noise_std_m)
            else:
                nx, ny, drift = _noise_sample(rng, scenario.noise_profile, drift)
            mx = x + nx
            my = y + ny
            if scenario.inject_single_outlier and abs(t - 2.5) < 0.5 * config.dt_s:
                mx += 0.45
                my -= 0.25
            out.append(Measurement(t, True, mx, my))
        else:
            out.append(Measurement(t, False))
    return out


def _err(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def run_tracker(measurements: Iterable[Measurement], config: RegimeConfig) -> List[TrackerOutput]:
    tracker = GhostRegimeTracker(config)
    return [tracker.step(m) for m in measurements]


def score_scenario(scenario: Scenario, measurements: List[Measurement], outputs: List[TrackerOutput], config: Optional[RegimeConfig] = None) -> ScenarioMetrics:
    cfg = config or RegimeConfig()
    errs = []
    hidden_outputs = []
    top1_terminal_errs = []
    top3_best_errs = []
    stationary_false_motions = []
    stationary_hold_hidden = 0
    first_hidden_model = "NONE"
    first_hidden_relative_weight = 0.0
    reset_count = 0

    for m, o in zip(measurements, outputs):
        truth = scenario.truth_fn(m.t_s)
        if o.x_m is not None and o.y_m is not None:
            errs.append(_err((o.x_m, o.y_m), truth))
        if not m.visible and o.initialized:
            hidden_outputs.append(o)
            if o.state_label == "HIDDEN - RESET REQUIRED":
                reset_count += 1
            if o.hidden_stationary_hold_active:
                stationary_hold_hidden += 1
            if o.hypotheses:
                terminal_truth = scenario.truth_fn(m.t_s + cfg.future_horizon_s)
                h_errs = [_err(h.terminal_xy(), terminal_truth) for h in o.hypotheses[:3]]
                top1_terminal_errs.append(h_errs[0])
                top3_best_errs.append(min(h_errs))
                if first_hidden_model == "NONE":
                    first_hidden_model = o.hypotheses[0].model
                    first_hidden_relative_weight = o.hypotheses[0].relative_hypothesis_weight
                h0 = o.hypotheses[0]
                if h0.path and o.x_m is not None and o.y_m is not None:
                    stationary_false_motions.append(_err((o.x_m, o.y_m), h0.terminal_xy()) / cfg.future_horizon_s)

    rmse = math.sqrt(statistics.fmean([e * e for e in errs])) if errs else math.nan
    p95 = sorted(errs)[int(0.95 * (len(errs) - 1))] if errs else math.nan
    top1 = statistics.fmean(top1_terminal_errs) if top1_terminal_errs else math.nan
    top3 = statistics.fmean(top3_best_errs) if top3_best_errs else math.nan
    false_motion = max(stationary_false_motions) if stationary_false_motions else 0.0
    hold_frac = stationary_hold_hidden / len(hidden_outputs) if hidden_outputs else 0.0

    passed = True
    notes = []
    if scenario.name == "stationary_hide_reveal":
        if first_hidden_model != "stationary_hold":
            passed = False
            notes.append("top hidden model was not stationary_hold")
        if first_hidden_relative_weight < cfg.stationary_prior_min:
            passed = False
            notes.append(f"stationary_hold prior below {cfg.stationary_prior_min:.2f}")
        if false_motion > cfg.stationary_false_motion_limit_mps:
            passed = False
            notes.append(f"dominant hidden path moved more than {cfg.stationary_false_motion_limit_mps:.3f} m/s")
        if hold_frac < cfg.stationary_hold_fraction_min:
            passed = False
            notes.append(f"stationary hold fraction below {cfg.stationary_hold_fraction_min:.2f}")
    elif scenario.name == "stationary_colored_noise_hide_reveal":
        if first_hidden_model != "stationary_hold":
            passed = False
            notes.append("colored-noise stationary case did not enter stationary_hold")
        if hold_frac < cfg.colored_noise_stationary_hold_fraction_min:
            passed = False
            notes.append(f"colored-noise hold fraction below {cfg.colored_noise_stationary_hold_fraction_min:.2f}")
        if false_motion > cfg.stationary_false_motion_limit_mps:
            passed = False
            notes.append(f"colored-noise hidden path moved more than {cfg.stationary_false_motion_limit_mps:.3f} m/s")
    elif scenario.name == "constant_velocity_hide_reveal":
        if first_hidden_model == "stationary_hold":
            passed = False
            notes.append("moving target incorrectly locked stationary")
    elif scenario.name == "move_then_stop_behind_wall":
        if top3 > cfg.stop_wall_top3_limit_m:
            passed = False
            notes.append(f"top3 future above stop-wall requirement {cfg.stop_wall_top3_limit_m:.2f} m")
    elif scenario.name == "lateral_hidden_motion":
        if top3 > cfg.lateral_top3_limit_m:
            passed = False
            notes.append(f"top3 future above lateral requirement {cfg.lateral_top3_limit_m:.2f} m")
    elif scenario.name == "long_occlusion_reset":
        if reset_count == 0:
            passed = False
            notes.append("long occlusion did not trigger reset/unknown state")
    elif scenario.name == "single_outlier_white_noise":
        if rmse > cfg.visible_rmse_limit_m:
            passed = False
            notes.append(f"visible RMSE above white-noise single-outlier requirement {cfg.visible_rmse_limit_m:.2f} m")

    return ScenarioMetrics(
        scenario.name,
        "PASS" if passed else "FAIL",
        len(outputs),
        len(hidden_outputs),
        rmse,
        p95,
        top1,
        top3,
        first_hidden_model,
        first_hidden_relative_weight,
        false_motion,
        hold_frac,
        reset_count,
        cfg.threshold_status,
        cfg.threshold_provenance,
        "; ".join(notes) if notes else "OK",
    )


def write_outputs(run_dir: Path, scenario: Scenario, measurements: List[Measurement], outputs: List[TrackerOutput], metrics: ScenarioMetrics) -> None:
    d = run_dir / scenario.name
    d.mkdir(parents=True, exist_ok=True)
    with (d / "measurements.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "visible", "x_m", "y_m"])
        for m in measurements:
            w.writerow([m.t_s, int(m.visible), "" if m.x_m is None else m.x_m, "" if m.y_m is None else m.y_m])
    with (d / "futures.jsonl").open("w", encoding="utf-8") as f:
        for o in outputs:
            f.write(json.dumps(o.to_json_dict(), separators=(",", ":")) + "\n")
    (d / "metrics.json").write_text(json.dumps(asdict(metrics), indent=2), encoding="utf-8")


def write_summary(run_dir: Path, metrics: List[ScenarioMetrics], config: Optional[RegimeConfig] = None) -> None:
    cfg = config or RegimeConfig()
    summary = {
        "overall_pass": all(m.pass_fail == "PASS" for m in metrics),
        "scenario_count": len(metrics),
        "pass_count": sum(1 for m in metrics if m.pass_fail == "PASS"),
        "fail_count": sum(1 for m in metrics if m.pass_fail != "PASS"),
        "threshold_status": cfg.threshold_status,
        "threshold_provenance": cfg.threshold_provenance,
        "acceptance_gates": {
            "stationary_false_motion_limit_mps": cfg.stationary_false_motion_limit_mps,
            "stationary_prior_min": cfg.stationary_prior_min,
            "stationary_hold_fraction_min": cfg.stationary_hold_fraction_min,
            "stop_wall_top3_limit_m": cfg.stop_wall_top3_limit_m,
            "lateral_top3_limit_m": cfg.lateral_top3_limit_m,
            "visible_rmse_limit_m": cfg.visible_rmse_limit_m,
        },
        "metrics": [asdict(m) for m in metrics],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# GHOST Software-Regime Acceptance Report\n",
        "This report is generated with no Pi, no camera, no ROS runtime, and synthetic known truth.\n",
        "> **Validation status:** Candidate placeholder harness. Do not cite this PASS result as real-world tracker validation until hardware-calibrated noise/threshold artifacts are committed and reviewed.\n",
        f"**Threshold status:** `{cfg.threshold_status}`  ",
        f"**Threshold provenance:** {cfg.threshold_provenance}\n",
        f"**Overall:** {'PASS' if summary['overall_pass'] else 'FAIL'}  ",
        f"**Scenarios:** {summary['pass_count']}/{summary['scenario_count']} passing\n",
        "| Scenario | Result | Top hidden model | Top relative weight | RMSE m | Top-1 future m | Top-3 best m | Stationary false motion m/s | Hold fraction | Reset count | Notes |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for m in metrics:
        lines.append(
            f"| {m.scenario} | {m.pass_fail} | {m.top1_model_at_first_hidden} | {m.top1_relative_hypothesis_weight_at_first_hidden:.2f} | "
            f"{m.rmse_m:.4f} | {m.top1_terminal_error_m:.4f} | {m.top3_best_terminal_error_m:.4f} | "
            f"{m.stationary_false_motion_mps:.4f} | {m.stationary_hold_fraction_hidden:.2f} | {m.reset_count} | {m.notes} |"
        )
    lines.append("\n## Acceptance Gates\n")
    lines.append(f"- `stationary_hide_reveal`: top hidden model must be `stationary_hold`, relative hypothesis weight >= {cfg.stationary_prior_min:.2f}, dominant hidden path <= {cfg.stationary_false_motion_limit_mps:.3f} m/s, hold fraction >= {cfg.stationary_hold_fraction_min:.2f}.")
    lines.append("- `stationary_colored_noise_hide_reveal`: synthetic AR(1) drift check only; not a replacement for hardware Allan/PSD replay.")
    lines.append("- `constant_velocity_hide_reveal`: moving target must not be incorrectly locked stationary.")
    lines.append("- `long_occlusion_reset`: V1 must eventually admit unknown/reset instead of claiming indefinite tracking.")
    lines.append("- Metrics use synthetic ground truth, not reacquisition as a truth proxy.\n")
    lines.append("## Known Limitations\n")
    lines.append("- Scenario pass/fail gates are explicit V1 engineering requirements/placeholders until traced to the design report.")
    lines.append("- `single_outlier_white_noise` is not a general false-measurement robustness test.")
    lines.append("- `stationary_colored_noise_hide_reveal` uses a synthetic AR(1) drift model, not yet the measured hardware noise replay.")
    lines.append("- This offline tracker class is a candidate implementation; live ROS tracker integration remains a separate PR.\n")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    html_rows = ["<table><tr><th>Scenario</th><th>Result</th><th>Top hidden model</th><th>False motion</th><th>Notes</th></tr>"]
    for m in metrics:
        cls = "pass" if m.pass_fail == "PASS" else "fail"
        html_rows.append(
            f"<tr><td>{html.escape(m.scenario)}</td><td class='{cls}'>{m.pass_fail}</td>"
            f"<td><code>{html.escape(m.top1_model_at_first_hidden)}</code></td><td>{m.stationary_false_motion_mps:.4f} m/s</td>"
            f"<td>{html.escape(m.notes)}</td></tr>"
        )
    html_rows.append("</table>")
    replay_html = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>GHOST Offline Replay</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;background:#111;color:#eee}}.card{{background:#1c1c1c;border:1px solid #333;border-radius:12px;padding:16px;margin:12px 0}}.warn{{background:#3a2f11;border:1px solid #8a6d1d;border-radius:12px;padding:12px}}.pass{{color:#7ddc7d;font-weight:700}}.fail{{color:#ff7777;font-weight:700}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #333;text-align:left;padding:8px}}code{{color:#9ed0ff}}</style></head><body>
<h1>GHOST Software-Regime Offline Replay</h1><p>No Pi. No camera. Synthetic truth and replay logs only.</p>
<div class=\"warn\"><strong>Candidate harness only.</strong> Threshold status: <code>{html.escape(cfg.threshold_status)}</code>. Do not cite PASS as real-world validation until hardware noise thresholds are committed.</div>
<div class=\"card\"><h2>Acceptance Summary</h2>{''.join(html_rows)}</div>
<div class=\"card\"><h2>Logs</h2><p>Each scenario folder contains <code>measurements.csv</code>, <code>futures.jsonl</code>, and <code>metrics.json</code>.</p></div>
</body></html>"""
    (run_dir / "replay.html").write_text(replay_html, encoding="utf-8")


def run_acceptance(out_dir: str) -> List[ScenarioMetrics]:
    cfg = RegimeConfig()
    run_dir = Path(out_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics: List[ScenarioMetrics] = []
    for scenario in make_scenarios().values():
        measurements = generate_measurements(scenario, cfg)
        outputs = run_tracker(measurements, cfg)
        m = score_scenario(scenario, measurements, outputs, cfg)
        metrics.append(m)
        write_outputs(run_dir, scenario, measurements, outputs, m)
    write_summary(run_dir, metrics, cfg)
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GHOST software-regime offline acceptance tests.")
    parser.add_argument("--out", default="ghost_regime_runs/latest")
    args = parser.parse_args()
    metrics = run_acceptance(args.out)
    report = Path(args.out) / "summary.md"
    print(report.read_text(encoding="utf-8"))
    return 0 if all(m.pass_fail == "PASS" for m in metrics) else 1


if __name__ == "__main__":
    raise SystemExit(main())
