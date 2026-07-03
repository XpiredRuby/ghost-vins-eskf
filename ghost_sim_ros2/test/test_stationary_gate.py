import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.stationary_gate import (  # noqa: E402
    CANDIDATE_THRESHOLD_STATUS,
    StationaryGateConfig,
    WindowedVelocityGate,
)


def colored_stationary_noise(count, dt, seed=11):
    """Synthetic colored AprilTag-like pose drift, not white measurement noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(count, dtype=float) * dt

    # AR(1) drift gives high lag-1 autocorrelation; slow sinusoid gives
    # low-frequency PSD concentration. The amplitudes are cm/sub-cm scale.
    drift_x = np.zeros(count)
    drift_y = np.zeros(count)
    phi = 0.995
    for k in range(1, count):
        drift_x[k] = phi * drift_x[k - 1] + rng.normal(0.0, 0.00015)
        drift_y[k] = phi * drift_y[k - 1] + rng.normal(0.0, 0.00015)

    x = 0.002 * np.sin(2.0 * np.pi * 0.12 * t) + drift_x + rng.normal(0.0, 0.0005, count)
    y = 0.002 * np.cos(2.0 * np.pi * 0.09 * t) + drift_y + rng.normal(0.0, 0.0005, count)
    return t, x, y


def run_gate(t, x, y, config):
    gate = WindowedVelocityGate(config)
    states = []
    for ti, xi, yi in zip(t, x, y):
        states.append(gate.update(float(ti), float(xi), float(yi)))
    return states


def test_default_thresholds_match_reviewed_candidate_values():
    config = StationaryGateConfig()

    assert config.window_s == 1.5
    assert config.enter_speed_mps == 0.065
    assert config.exit_speed_mps == 0.090
    assert config.threshold_status == CANDIDATE_THRESHOLD_STATUS
    assert "hardware-calibrated" in config.threshold_provenance


def test_stationary_colored_noise_enters_and_stays_locked():
    config = StationaryGateConfig(
        window_s=1.5,
        enter_speed_mps=0.065,
        exit_speed_mps=0.090,
        min_samples=8,
    )
    t, x, y = colored_stationary_noise(count=1200, dt=0.05)

    states = run_gate(t, x, y, config)
    initialized = [s for s in states if s.initialized]

    assert initialized
    assert any(s.active for s in initialized)

    # Ignore warmup. After lock, colored stationary noise should not repeatedly
    # kick the gate out as long as thresholds are set above the measured noise floor.
    post_warmup = [s for s in initialized if s.span_s >= config.window_s * 0.9][-500:]
    assert post_warmup
    assert sum(1 for s in post_warmup if s.active) / len(post_warmup) > 0.95
    assert post_warmup[-1].suppress_dynamic_hypotheses


def test_slow_constant_motion_does_not_false_lock():
    config = StationaryGateConfig(
        window_s=1.5,
        enter_speed_mps=0.065,
        exit_speed_mps=0.090,
        min_samples=8,
    )
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)
    x = 0.10 * t
    y = np.zeros_like(t)

    states = run_gate(t, x, y, config)
    initialized = [s for s in states if s.initialized]

    assert initialized
    assert not any(s.active for s in initialized)
    assert math.isclose(initialized[-1].speed_mps, 0.10, rel_tol=0.05)


def test_stationary_to_motion_to_stationary_transition():
    config = StationaryGateConfig(
        window_s=1.0,
        enter_speed_mps=0.065,
        exit_speed_mps=0.090,
        min_samples=6,
    )
    dt = 0.05
    t = np.arange(0.0, 15.0, dt)
    x = np.zeros_like(t)
    y = np.zeros_like(t)

    for k, ti in enumerate(t):
        if 5.0 <= ti < 10.0:
            x[k] = 0.15 * (ti - 5.0)
        elif ti >= 10.0:
            x[k] = 0.15 * 5.0

    states = run_gate(t, x, y, config)

    before_motion = [s for ti, s in zip(t, states) if 3.0 <= ti < 4.5 and s.initialized]
    during_motion = [s for ti, s in zip(t, states) if 7.0 <= ti < 9.0 and s.initialized]
    after_stop = [s for ti, s in zip(t, states) if 12.0 <= ti < 14.5 and s.initialized]

    assert before_motion and before_motion[-1].active
    assert during_motion and not during_motion[-1].active
    assert after_stop and after_stop[-1].active


def test_config_validation_rejects_bad_hysteresis():
    config = StationaryGateConfig(window_s=1.0, enter_speed_mps=0.10, exit_speed_mps=0.05)

    try:
        WindowedVelocityGate(config)
    except ValueError as exc:
        assert "exit_speed_mps" in str(exc)
    else:
        raise AssertionError("bad hysteresis config should raise ValueError")


def test_nonmonotonic_timestamps_are_rejected():
    gate = WindowedVelocityGate(StationaryGateConfig())
    gate.update(1.0, 0.0, 0.0)

    try:
        gate.update(0.9, 0.0, 0.0)
    except ValueError as exc:
        assert "timestamps" in str(exc)
    else:
        raise AssertionError("nonmonotonic timestamps should raise ValueError")
