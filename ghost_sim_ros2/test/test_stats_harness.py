import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.stats_harness import (  # noqa: E402
    format_markdown,
    read_csv_rows,
    summarize_rows,
    write_summary_csv,
)


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_summary_mean_std_and_ci():
    rows = [{"metric": "1.0"}, {"metric": "2.0"}, {"metric": "3.0"}]

    summary = summarize_rows(rows, ["metric"])[0]

    assert summary.count == 3
    assert math.isclose(summary.mean, 2.0)
    assert math.isclose(summary.std, 1.0)
    assert math.isclose(summary.stderr, 1.0 / math.sqrt(3.0))
    assert summary.ci95_low < summary.mean < summary.ci95_high


def test_summary_groups_by_scenario():
    rows = [
        {"scenario": "a", "rmse": "1.0"},
        {"scenario": "a", "rmse": "3.0"},
        {"scenario": "b", "rmse": "10.0"},
    ]

    summaries = summarize_rows(rows, ["rmse"], group_by=["scenario"])
    by_group = {summary.group["scenario"]: summary for summary in summaries}

    assert math.isclose(by_group["a"].mean, 2.0)
    assert math.isclose(by_group["b"].mean, 10.0)


def test_summary_ignores_missing_and_nonfinite_values():
    rows = [{"rmse": "1.0"}, {"rmse": ""}, {"rmse": "nan"}, {"rmse": "5.0"}]

    summary = summarize_rows(rows, ["rmse"])[0]

    assert summary.count == 2
    assert math.isclose(summary.mean, 3.0)


def test_csv_read_write_round_trip(tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "summary.csv"
    write_csv(input_path, [{"scenario": "a", "rmse": "1.0"}, {"scenario": "a", "rmse": "2.0"}])

    rows = read_csv_rows(input_path)
    summaries = summarize_rows(rows, ["rmse"], group_by=["scenario"])
    write_summary_csv(output_path, summaries)

    assert output_path.exists()
    assert "scenario=a" in output_path.read_text()


def test_markdown_contains_metric_table():
    summaries = summarize_rows([{"rmse": "1.0"}, {"rmse": "2.0"}], ["rmse"])

    text = format_markdown(summaries)

    assert "GHOST Statistics Summary" in text
    assert "rmse" in text
    assert "95% CI" in text
