import math

from analysis.ghost_mh_mode_bank import ModeBankTracker
from analysis.ghost_mh_multi_future_benchmark import parse_args, run_benchmark


def test_mode_bank_branches_once_during_occlusion():
    tracker = ModeBankTracker()
    tracker.initialize([0.0, 0.0], [0.4, 0.0])
    tracker.was_visible = True
    tracker.step(0.1, None)
    first_count = len(tracker.hypotheses)
    tracker.step(0.1, None)
    assert first_count > 1
    assert len(tracker.hypotheses) == first_count
    assert abs(sum(h.weight for h in tracker.hypotheses) - 1.0) < 1e-9


def test_mode_bank_stops_after_occlusion_horizon():
    tracker = ModeBankTracker(max_occlusion_s=0.2)
    tracker.initialize([0.0, 0.0], [0.4, 0.0])
    tracker.was_visible = True
    tracker.step(0.15, None)
    assert tracker.initialized
    tracker.step(0.15, None)
    assert not tracker.initialized


def test_multi_future_benchmark_reports_coverage():
    args = parse_args([])
    args.duration = 6.0
    args.rate = 20.0
    args.noise_std = 0.035
    args.seeds = "7"
    args.scenarios = "turn_left"
    args.occlusion_starts = "3.0"
    args.occlusion_durations = "1.0"
    args.coverage_radius = 0.25
    rows = run_benchmark(args)
    assert rows
    assert math.isfinite(rows[0]["mh_future_coverage_frac"])


def test_mode_bank_uses_full_measurement_covariance_exactly():
    import numpy as np

    r = ((2.17492633008e-06, 6.31889067707e-07), (6.31889067707e-07, 1.98048863448e-07))
    tracker = ModeBankTracker(measurement_std_m=0.005, measurement_covariance_xy=r)

    assert np.allclose(tracker.r, np.asarray(r))
    assert tracker.measurement_r_xy == [[r[0][0], r[0][1]], [r[1][0], r[1][1]]]
    assert tracker.measurement_r_status == "DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY"
