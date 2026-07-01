import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str


SCENARIOS = [
    Scenario("straight", "constant-velocity straight target"),
    Scenario("turn_left", "smooth left maneuver"),
    Scenario("turn_right", "smooth right maneuver"),
    Scenario("evasive_brake", "braking target with sinusoidal lateral motion"),
    Scenario("s_curve", "alternating lateral acceleration"),
    Scenario("accel_burst", "forward acceleration burst before occlusion"),
    Scenario("hover_then_escape", "near-hover followed by lateral escape"),
]


def scenario_names() -> list[str]:
    return [scenario.name for scenario in SCENARIOS]


def truth_state(t: float, scenario: str) -> np.ndarray:
    if scenario == "straight":
        return np.array([[0.35 + 0.36 * t], [-0.18 + 0.03 * t], [0.36], [0.03]], dtype=float)

    if scenario == "turn_left":
        if t < 5.0:
            return np.array([[0.35 + 0.32 * t], [-0.25 + 0.05 * t], [0.32], [0.05]], dtype=float)
        tau = t - 5.0
        return np.array(
            [[1.95 + 0.30 * tau - 0.035 * tau * tau],
             [0.00 + 0.05 * tau + 0.055 * tau * tau],
             [0.30 - 0.07 * tau],
             [0.05 + 0.11 * tau]],
            dtype=float,
        )

    if scenario == "turn_right":
        if t < 5.0:
            return np.array([[0.35 + 0.32 * t], [0.35 - 0.04 * t], [0.32], [-0.04]], dtype=float)
        tau = t - 5.0
        return np.array(
            [[1.95 + 0.30 * tau - 0.030 * tau * tau],
             [0.15 - 0.04 * tau - 0.060 * tau * tau],
             [0.30 - 0.06 * tau],
             [-0.04 - 0.12 * tau]],
            dtype=float,
        )

    if scenario == "evasive_brake":
        if t < 4.0:
            return np.array([[0.35 + 0.42 * t], [-0.20 + 0.02 * t], [0.42], [0.02]], dtype=float)
        tau = t - 4.0
        vx = max(0.03, 0.42 - 0.16 * tau)
        vy = 0.02 + 0.18 * math.sin(1.2 * tau)
        x = 2.03 + 0.42 * tau - 0.08 * tau * tau
        y = -0.12 + 0.02 * tau + 0.15 * (1.0 - math.cos(1.2 * tau))
        return np.array([[x], [y], [vx], [vy]], dtype=float)

    if scenario == "s_curve":
        x = 0.35 + 0.34 * t
        y = 0.45 * math.sin(0.62 * t)
        vx = 0.34
        vy = 0.279 * math.cos(0.62 * t)
        return np.array([[x], [y], [vx], [vy]], dtype=float)

    if scenario == "accel_burst":
        if t < 4.5:
            return np.array([[0.30 + 0.22 * t], [-0.16], [0.22], [0.0]], dtype=float)
        tau = t - 4.5
        return np.array(
            [[1.29 + 0.22 * tau + 0.12 * tau * tau],
             [-0.16 + 0.015 * tau],
             [0.22 + 0.24 * tau],
             [0.015]],
            dtype=float,
        )

    if scenario == "hover_then_escape":
        if t < 4.0:
            return np.array([[0.85 + 0.015 * t], [0.10], [0.015], [0.0]], dtype=float)
        tau = t - 4.0
        return np.array(
            [[0.91 + 0.06 * tau],
             [0.10 + 0.16 * tau + 0.045 * tau * tau],
             [0.06],
             [0.16 + 0.09 * tau]],
            dtype=float,
        )

    raise ValueError(f"unknown scenario: {scenario}")


def in_occlusion(t: float, start: float, duration: float) -> bool:
    return start <= t < start + duration
