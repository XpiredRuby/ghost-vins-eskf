import math

from analysis.ghost_mh_benchmark import parse_args, run_benchmark, summarize
from analysis.ghost_mh_engine import MultiHypothesisTracker


def test_mh_tracker_normalizes_branch_weights():
    tracker = MultiHypothesisTracker(max_hypotheses=12)
    tracker.initialize([0.0, 0.0], [0.5, 0.0])
    tracker.step(0.1, None)
    total = sum(h.weight for h in tracker.hypotheses)
    assert tracker.initialized
    assert len(tracker.hypotheses) > 1
    assert abs(total - 1.0) < 1e-9


def test_mh_tracker_stops_after_occlusion_horizon():
    tracker = MultiHypothesisTracker(max_occlusion_s=0.3)
    tracker.initialize([0.0, 0.0], [0.5, 0.0])
    tracker.step(0.2, None)
    assert tracker.initialized
    tracker.step(0.2, None)
    assert not tracker.initialized


def test_mh_benchmark_runs_and_reports_errors():
    args = parse_args()
    args.duration = 5.0
    args.rate = 20.0
    args.noise_std = 0.035
    args.occlusion_start = 2.0
    args.occlusion_duration = 1.0
    args.seed = 11
    rows = run_benchmark(args)
    summary = summarize(rows, args)
    assert rows
    assert math.isfinite(summary["occlusion_cv_rmse_m"])
    assert math.isfinite(summary["occlusion_mh_rmse_m"])
