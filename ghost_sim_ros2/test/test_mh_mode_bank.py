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
    args = parse_args()
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
