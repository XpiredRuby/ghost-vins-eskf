import math
from collections import deque
from typing import Iterable

import numpy as np

from analysis.ghost_mh_engine import MEAS_DIM, MotionModel, _as_col
from analysis.ghost_mh_mode_bank import ModeBankTracker, mode_bank


class CalibratedModeBankTracker(ModeBankTracker):
    """Mode-bank tracker with motion-trend calibrated branch priors.

    The mode-bank tracker is intentionally multi-modal: it carries several
    possible futures during occlusion. This calibrated version changes only the
    initial branch relative weights at the moment the target disappears. It uses the
    recent visible measurement trend to bias priors toward modes consistent with
    the observed velocity/acceleration without re-branching every hidden frame.
    """

    def __init__(
        self,
        history_len: int = 8,
        accel_temperature: float = 0.30,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.history: deque[tuple[float, np.ndarray]] = deque(maxlen=history_len)
        self.time_s = 0.0
        self.accel_temperature = float(accel_temperature)

    def step(self, dt: float, measurement_xy: Iterable[float] | None) -> bool:
        self.time_s += max(0.0, float(dt))
        if measurement_xy is not None:
            z = _as_col(measurement_xy, MEAS_DIM)
            self.history.append((self.time_s, z.copy()))

        if measurement_xy is None and self.was_visible:
            self.models = self.calibrated_mode_bank()
        return super().step(dt, measurement_xy)

    def calibrated_mode_bank(self) -> list[MotionModel]:
        base = mode_bank()
        vx, vy, ax, ay = self.motion_trend()
        speed = math.hypot(vx, vy)
        accel_norm = math.hypot(ax, ay)

        scored = []
        for model in base:
            score = math.log(max(model.prior, 1e-9))
            model_accel_norm = math.hypot(model.ax_mps2, model.ay_mps2)

            if accel_norm < 0.10:
                if model.name == "constant_velocity":
                    score += 0.55
                if model.name == "brake_or_hover" and speed < 0.20:
                    score += 0.25
            elif model_accel_norm > 1e-9:
                alignment = (model.ax_mps2 * ax + model.ay_mps2 * ay) / (
                    model_accel_norm * accel_norm
                )
                score += alignment / max(self.accel_temperature, 1e-6)

            if model.name == "brake_or_hover" and speed > 0.05:
                vdot_a = vx * ax + vy * ay
                if vdot_a < 0.0:
                    score += 0.35

            scored.append((model, score))

        max_score = max(score for _, score in scored)
        weights = [math.exp(score - max_score) for _, score in scored]
        total = sum(weights)
        calibrated = []
        for (model, _), weight in zip(scored, weights):
            calibrated.append(
                MotionModel(
                    model.name,
                    ax_mps2=model.ax_mps2,
                    ay_mps2=model.ay_mps2,
                    speed_scale=model.speed_scale,
                    process_accel_std_mps2=model.process_accel_std_mps2,
                    prior=weight / total,
                )
            )
        return calibrated

    def motion_trend(self) -> tuple[float, float, float, float]:
        if len(self.history) < 4:
            return 0.0, 0.0, 0.0, 0.0

        samples = list(self.history)
        t0 = samples[-1][0]
        ts = np.array([t - t0 for t, _ in samples], dtype=float)
        xs = np.array([float(z[0, 0]) for _, z in samples], dtype=float)
        ys = np.array([float(z[1, 0]) for _, z in samples], dtype=float)
        design = np.column_stack([np.ones_like(ts), ts, 0.5 * ts * ts])
        try:
            coef_x, *_ = np.linalg.lstsq(design, xs, rcond=None)
            coef_y, *_ = np.linalg.lstsq(design, ys, rcond=None)
        except np.linalg.LinAlgError:
            return 0.0, 0.0, 0.0, 0.0

        return float(coef_x[1]), float(coef_y[1]), float(coef_x[2]), float(coef_y[2])
