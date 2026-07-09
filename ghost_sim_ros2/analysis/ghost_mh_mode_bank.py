import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from analysis.measurement_covariance_config import (
    build_measurement_r_xy,
    covariance_to_list,
    measurement_r_provenance,
    measurement_r_source,
    measurement_r_status,
)
from analysis.ghost_mh_engine import (
    MEAS_DIM,
    STATE_DIM,
    Estimate,
    Hypothesis,
    MotionModel,
    _as_col,
    _cv_matrix,
    _gaussian_likelihood,
    _process_noise,
)


def mode_bank() -> list[MotionModel]:
    return [
        MotionModel("constant_velocity", process_accel_std_mps2=0.65, prior=0.34),
        MotionModel("brake_or_hover", speed_scale=0.88, process_accel_std_mps2=0.45, prior=0.16),
        MotionModel("coordinated_turn_left", ax_mps2=-0.07, ay_mps2=0.11, process_accel_std_mps2=0.55, prior=0.16),
        MotionModel("coordinated_turn_right", ax_mps2=-0.07, ay_mps2=-0.11, process_accel_std_mps2=0.55, prior=0.14),
        MotionModel("accelerate_forward", ax_mps2=0.28, process_accel_std_mps2=0.90, prior=0.08),
        MotionModel("lateral_left", ay_mps2=0.26, process_accel_std_mps2=0.90, prior=0.05),
        MotionModel("lateral_right", ay_mps2=-0.26, process_accel_std_mps2=0.90, prior=0.05),
        MotionModel("evasive_maneuver", process_accel_std_mps2=1.8, prior=0.02),
    ]


@dataclass
class ModeHypothesis(Hypothesis):
    branched: bool = False


class ModeBankTracker:
    """GHOST-MH v2 candidate with persistent motion modes.

    Unlike the first MH prototype, this tracker does not branch every hidden
    frame. It branches once when measurements disappear, then each hypothesis
    keeps its assigned physical mode until reacquisition. That makes the belief
    tree interpretable and prevents excessive probability diffusion.
    """

    def __init__(
        self,
        models: list[MotionModel] | None = None,
        max_occlusion_s: float = 3.0,
        max_workspace_range_m: float = 8.0,
        measurement_std_m: float = 0.05,
        gate_chi2: float = 16.0,
        measurement_covariance_xy: Iterable[Iterable[float]] | None = None,
    ):
        self.models = models if models is not None else mode_bank()
        self.max_occlusion_s = float(max_occlusion_s)
        self.max_workspace_range_m = float(max_workspace_range_m)
        self.measurement_std_m = float(measurement_std_m)
        self.measurement_covariance_xy = (
            tuple(tuple(float(v) for v in row) for row in measurement_covariance_xy)
            if measurement_covariance_xy is not None
            else None
        )
        self.gate_chi2 = float(gate_chi2)
        self.h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)
        self.r = np.asarray(
            build_measurement_r_xy(
                self.measurement_std_m,
                self.measurement_covariance_xy[0][0] if self.measurement_covariance_xy is not None else None,
                self.measurement_covariance_xy[0][1] if self.measurement_covariance_xy is not None else 0.0,
                self.measurement_covariance_xy[1][1] if self.measurement_covariance_xy is not None else None,
            ),
            dtype=float,
        )
        self.measurement_r_xy = covariance_to_list(self.r)
        self.measurement_r_source = measurement_r_source(self.measurement_covariance_xy, self.measurement_std_m)
        self.measurement_r_status = measurement_r_status(self.measurement_covariance_xy)
        self.measurement_r_provenance = measurement_r_provenance(self.measurement_covariance_xy)
        self.hypotheses: list[ModeHypothesis] = []
        self.was_visible = False

    @property
    def initialized(self) -> bool:
        return bool(self.hypotheses)

    def initialize(
        self,
        z_xy: Iterable[float],
        velocity_xy: Iterable[float] = (0.0, 0.0),
        position_var_m2: float = 0.04,
        velocity_var_m2ps2: float = 0.8,
    ) -> None:
        z = _as_col(z_xy, MEAS_DIM)
        v = _as_col(velocity_xy, MEAS_DIM)
        x = np.array([[z[0, 0]], [z[1, 0]], [v[0, 0]], [v[1, 0]]], dtype=float)
        p = np.diag([position_var_m2, position_var_m2, velocity_var_m2ps2, velocity_var_m2ps2])
        self.hypotheses = [ModeHypothesis("visible_cv", 1.0, x, p, 0.0, False)]

    def step(self, dt: float, measurement_xy: Iterable[float] | None) -> bool:
        visible = measurement_xy is not None
        self.predict(dt, visible)
        if not visible:
            self.hypotheses = [
                hyp for hyp in self.hypotheses if hyp.age_s <= self.max_occlusion_s
            ]
            self.was_visible = False
            return False

        accepted = self.update(measurement_xy)
        self.was_visible = True
        return accepted

    def predict(self, dt: float, visible: bool) -> None:
        if not self.hypotheses or dt <= 0.0:
            return

        predicted: list[ModeHypothesis] = []
        if visible:
            model = MotionModel("visible_cv", process_accel_std_mps2=0.70, prior=1.0)
            for hyp in self.hypotheses:
                child = self._predict_one(hyp, model, dt, reset_age=True, branched=False)
                if self._is_reasonable(child, allow_age=True):
                    predicted.append(child)
        elif self.was_visible or len(self.hypotheses) == 1 and not self.hypotheses[0].branched:
            source = self.estimate()
            if not source.initialized:
                return
            for model in self.models:
                hyp = ModeHypothesis(model.name, model.prior, source.x.copy(), source.p.copy(), 0.0, True)
                child = self._predict_one(hyp, model, dt, reset_age=False, branched=True)
                if self._is_reasonable(child):
                    predicted.append(child)
        else:
            lookup = {model.name: model for model in self.models}
            for hyp in self.hypotheses:
                model = lookup.get(hyp.model, self.models[0])
                child = self._predict_one(hyp, model, dt, reset_age=False, branched=True)
                if self._is_reasonable(child):
                    predicted.append(child)

        if not predicted:
            self.hypotheses = []
            return
        self.hypotheses = self._normalize(predicted)

    def update(self, measurement_xy: Iterable[float]) -> bool:
        z = _as_col(measurement_xy, MEAS_DIM)
        if not self.hypotheses:
            self.initialize([z[0, 0], z[1, 0]])
            return True

        updated = []
        for hyp in self.hypotheses:
            innovation = z - self.h @ hyp.x
            s = self.h @ hyp.p @ self.h.T + self.r
            try:
                inv_s = np.linalg.inv(s)
                nis = float((innovation.T @ inv_s @ innovation)[0, 0])
            except np.linalg.LinAlgError:
                continue
            if nis > self.gate_chi2:
                continue
            k = hyp.p @ self.h.T @ inv_s
            eye = np.eye(STATE_DIM)
            x = hyp.x + k @ innovation
            p = (eye - k @ self.h) @ hyp.p @ (eye - k @ self.h).T + k @ self.r @ k.T
            likelihood = _gaussian_likelihood(innovation, s)
            updated.append(ModeHypothesis(hyp.model, hyp.weight * likelihood, x, p, 0.0, False))

        if not updated:
            return False
        self.hypotheses = self._collapse_after_update(updated)
        return True

    def estimate(self) -> Estimate:
        if not self.hypotheses:
            return Estimate(False, np.zeros((STATE_DIM, 1)), np.eye(STATE_DIM), [])
        x = sum(hyp.weight * hyp.x for hyp in self.hypotheses)
        p = np.zeros((STATE_DIM, STATE_DIM), dtype=float)
        for hyp in self.hypotheses:
            dx = hyp.x - x
            p += hyp.weight * (hyp.p + dx @ dx.T)
        return Estimate(True, x, p, list(self.hypotheses))

    def top_hypotheses(self, n: int = 5) -> list[ModeHypothesis]:
        return sorted(self.hypotheses, key=lambda hyp: hyp.weight, reverse=True)[:n]

    def _predict_one(
        self,
        hyp: ModeHypothesis,
        model: MotionModel,
        dt: float,
        reset_age: bool,
        branched: bool,
    ) -> ModeHypothesis:
        f = _cv_matrix(dt)
        x = f @ hyp.x
        x[0, 0] += 0.5 * model.ax_mps2 * dt * dt
        x[1, 0] += 0.5 * model.ay_mps2 * dt * dt
        x[2, 0] = model.speed_scale * (x[2, 0] + model.ax_mps2 * dt)
        x[3, 0] = model.speed_scale * (x[3, 0] + model.ay_mps2 * dt)
        p = f @ hyp.p @ f.T + _process_noise(dt, model.process_accel_std_mps2)
        age = 0.0 if reset_age else hyp.age_s + dt
        return ModeHypothesis(model.name, hyp.weight, x, p, age, branched)

    def _is_reasonable(self, hyp: ModeHypothesis, allow_age: bool = False) -> bool:
        if not allow_age and hyp.age_s > self.max_occlusion_s:
            return False
        px = float(hyp.x[0, 0])
        py = float(hyp.x[1, 0])
        return px >= -0.25 and math.hypot(px, py) <= self.max_workspace_range_m

    def _collapse_after_update(self, hypotheses: list[ModeHypothesis]) -> list[ModeHypothesis]:
        normalized = self._normalize(hypotheses)
        estimate = ModeBankTracker(
            measurement_std_m=self.measurement_std_m,
            measurement_covariance_xy=self.measurement_covariance_xy,
        )
        estimate.hypotheses = normalized
        est = estimate.estimate()
        return [ModeHypothesis("visible_cv", 1.0, est.x, est.p, 0.0, False)]

    def _normalize(self, hypotheses: list[ModeHypothesis]) -> list[ModeHypothesis]:
        total = sum(max(0.0, hyp.weight) for hyp in hypotheses)
        if total <= 0.0 or not math.isfinite(total):
            uniform = 1.0 / len(hypotheses)
            for hyp in hypotheses:
                hyp.weight = uniform
            return hypotheses
        for hyp in hypotheses:
            hyp.weight = max(0.0, hyp.weight) / total
        return sorted(hypotheses, key=lambda hyp: hyp.weight, reverse=True)
