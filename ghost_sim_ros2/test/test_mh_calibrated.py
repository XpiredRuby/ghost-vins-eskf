import math

from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.ghost_mh_export_futures import parse_args as export_parse_args
from analysis.ghost_mh_export_futures import run_export
from analysis.ghost_mh_final_no_camera_benchmark import parse_args, run_benchmark


def test_calibrated_mode_bank_priors_normalize_on_occlusion():
    tracker = CalibratedModeBankTracker(measurement_std_m=0.035)
    for i in range(8):
        tracker.step(0.05, [0.2 + 0.03 * i, -0.1 + 0.002 * i])
    tracker.step(0.05, None)

    assert tracker.initialized
    assert len(tracker.hypotheses) > 1
    assert abs(sum(h.weight for h in tracker.hypotheses) - 1.0) < 1e-9


def test_final_no_camera_benchmark_reports_calibrated_coverage():
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
    assert math.isfinite(rows[0]["calibrated_top3_coverage_frac"])
    assert rows[0]["calibrated_best_beats_cv"] in (0, 1)


def test_future_export_emits_ranked_hypotheses():
    args = export_parse_args()
    args.duration = 6.0
    args.rate = 20.0
    args.seed = 7
    args.scenario = "turn_left"
    args.occlusion_start = 3.0
    args.occlusion_duration = 1.0
    args.top_n = 3
    rows = run_export(args)

    assert rows
    assert max(row["rank"] for row in rows) <= 3
    assert any(row["visible"] == 0 for row in rows)
