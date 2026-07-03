import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.acceptance_gate import (  # noqa: E402
    evaluate_tracker_comparison,
    format_report,
    mean_indicator,
    mean_metric,
    parse_float,
)


def passing_rows():
    return [
        {
            "mh_top3_beats_cv": "1",
            "mh_top3_coverage_frac": "0.8",
            "cv_rmse_m": "0.5",
            "mh_top3_future_rmse_m": "0.2",
        },
        {
            "mh_top3_beats_cv": "0",
            "mh_top3_coverage_frac": "0.7",
            "cv_rmse_m": "0.7",
            "mh_top3_future_rmse_m": "0.3",
        },
        {
            "mh_top3_beats_cv": "1",
            "mh_top3_coverage_frac": "0.9",
            "cv_rmse_m": "0.6",
            "mh_top3_future_rmse_m": "0.25",
        },
    ]


def test_mean_indicator_counts_binary_successes():
    assert math.isclose(mean_indicator(passing_rows(), "mh_top3_beats_cv"), 2.0 / 3.0)


def test_mean_metric_ignores_missing_values():
    rows = [{"metric": "1.0"}, {"metric": ""}, {"metric": "3.0"}]

    assert math.isclose(mean_metric(rows, "metric"), 2.0)


def test_parse_float_returns_nan_for_bad_values():
    assert math.isnan(parse_float(""))
    assert math.isnan(parse_float("nope"))
    assert math.isclose(parse_float("1.25"), 1.25)


def test_tracker_comparison_gate_passes_expected_rows():
    results = evaluate_tracker_comparison(
        passing_rows(),
        min_mh_top3_win_frac=0.60,
        min_mh_top3_coverage=0.75,
        max_mean_cv_rmse=1.0,
        max_mean_mh_top3_rmse=0.5,
    )

    assert all(result.passed for result in results)
    assert "Overall: PASS" in format_report(results)


def test_tracker_comparison_gate_fails_strict_threshold():
    results = evaluate_tracker_comparison(
        passing_rows(),
        min_mh_top3_win_frac=0.90,
        min_mh_top3_coverage=0.95,
    )

    assert not all(result.passed for result in results)
    assert "Overall: FAIL" in format_report(results)


def test_empty_rows_are_rejected():
    try:
        evaluate_tracker_comparison([])
    except ValueError as exc:
        assert "no rows" in str(exc)
    else:
        raise AssertionError("empty benchmark should raise ValueError")
