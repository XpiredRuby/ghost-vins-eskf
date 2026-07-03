import math
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.tracker_comparison import (  # noqa: E402
    TrialSpec,
    mean,
    parse_float_list,
    parse_int_list,
    parse_str_list,
    rmse,
    run_comparison,
    run_trial,
    safe_frac,
    write_rows,
)


def small_args(**overrides):
    values = {
        "duration": 7.0,
        "rate": 10.0,
        "noise_std": 0.01,
        "seeds": "1,2",
        "scenarios": "straight,turn_left",
        "occlusion_starts": "3.0",
        "occlusion_durations": "1.0,1.5",
        "coverage_radius": 0.25,
        "accel_temperature": 0.30,
    }
    values.update(overrides)
    return Namespace(**values)


def test_parse_helpers_strip_empty_items():
    assert parse_float_list("1.0, 2.5,") == [1.0, 2.5]
    assert parse_int_list("7, 11") == [7, 11]
    assert parse_str_list("straight, turn_left") == ["straight", "turn_left"]


def test_math_helpers_ignore_nonfinite_values():
    assert math.isclose(rmse([3.0, 4.0, math.nan]), math.sqrt(12.5))
    assert math.isclose(mean([1.0, math.nan, 3.0]), 2.0)
    assert math.isnan(safe_frac(1, 0))
    assert math.isclose(safe_frac(3, 4), 0.75)


def test_single_trial_contains_all_tracker_metrics():
    args = small_args()
    row = run_trial(args, TrialSpec("straight", 1, 3.0, 1.0))

    assert row["scenario"] == "straight"
    assert math.isfinite(row["cv_rmse_m"])
    assert math.isfinite(row["imm_rmse_m"])
    assert math.isfinite(row["mh_top3_future_rmse_m"])
    assert 0.0 <= row["mh_top3_coverage_frac"] <= 1.0
    assert row["mh_top3_future_rmse_m"] <= row["mh_mean_rmse_m"]
    assert row["imm_beats_cv"] in (0, 1)
    assert row["mh_top3_beats_cv"] in (0, 1)


def test_comparison_generates_cartesian_trial_grid():
    rows = run_comparison(small_args())

    assert len(rows) == 8
    scenarios = {row["scenario"] for row in rows}
    durations = {row["occlusion_duration_s"] for row in rows}
    assert scenarios == {"straight", "turn_left"}
    assert durations == {1.0, 1.5}


def test_write_rows_round_trip(tmp_path):
    path = tmp_path / "comparison.csv"
    rows = run_comparison(small_args(scenarios="straight", seeds="1", occlusion_durations="1.0"))

    write_rows(path, rows)
    text = path.read_text()

    assert "cv_rmse_m" in text
    assert "imm_rmse_m" in text
    assert "mh_top3_future_rmse_m" in text
