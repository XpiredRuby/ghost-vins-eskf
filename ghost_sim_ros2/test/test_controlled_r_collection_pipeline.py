import csv
import json
import math
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.controlled_r_collection_quality import (  # noqa: E402
    ACCEPTABLE,
    PoseSample,
    REJECT,
    evaluate_collection,
    evaluate_path,
)
from analysis.controlled_r_protocol_analysis import (  # noqa: E402
    CsvSample,
    analyze_controlled_r,
    load_pose_csv,
    write_outputs,
)


def _pose_samples(rate_hz: float = 13.5, duration_s: float = 90.0):
    dt = 1.0 / rate_hz
    count = int(duration_s * rate_hz) + 1
    return [
        PoseSample(t_s=k * dt, x_m=1.0, y_m=0.2, z_m=0.0)
        for k in range(count)
    ]


def test_collection_quality_accepts_full_rate_fixed_window():
    summary = evaluate_collection(_pose_samples())

    assert summary["status"] == ACCEPTABLE
    assert summary["acceptable"] is True
    assert summary["analysis_rate_hz"] >= 13.4
    assert summary["max_analysis_gap_s"] < 0.08
    assert summary["errors"] == []


def test_collection_quality_rejects_low_rate_and_large_gap():
    samples = _pose_samples(rate_hz=5.0)
    summary = evaluate_collection(samples)

    assert summary["status"] == REJECT
    assert any("below declared minimum" in error for error in summary["errors"])


def test_collection_quality_rejects_short_record():
    summary = evaluate_collection(_pose_samples(duration_s=70.0))

    assert summary["status"] == REJECT
    assert any("does not cover" in error for error in summary["errors"])


def test_collection_quality_reports_malformed_jsonl(tmp_path: Path):
    path = tmp_path / "vision_pose.jsonl"
    path.write_text('{"t_rel_s": 0.0, "position": {"x_m": 1.0}}\n', encoding="utf-8")

    summary = evaluate_path(path)

    assert summary["status"] == REJECT
    assert summary["acceptable"] is False
    assert summary["errors"]


def _csv_samples():
    rows = []
    for k in range(1201):
        t = k * 0.075
        x = 1.0 + 0.001 * math.sin(0.31 * k) + 0.00001 * t
        y = 0.2 + 0.0005 * math.cos(0.23 * k) - 0.00002 * t
        rows.append(CsvSample(t_s=t, x_m=x, y_m=y, z_m=0.0))
    return rows


def test_protocol_analysis_reports_primary_and_three_subwindows():
    summary = analyze_controlled_r(_csv_samples())

    primary = summary["primary_window"]
    assert primary["start_s"] == 15.0
    assert primary["end_s"] == 75.0
    assert primary["sample_count"] > 700
    assert primary["r_xx_m2"] > 0.0
    assert primary["r_yy_m2"] > 0.0
    assert -1.0 <= primary["correlation_xy"] <= 1.0
    assert len(summary["subwindows"]) == 3
    assert summary["stability_diagnostics"]["subwindow_count"] == 3


def test_protocol_analysis_csv_and_outputs_round_trip(tmp_path: Path):
    csv_path = tmp_path / "vision_pose_log.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "x", "y", "z"])
        for row in _csv_samples():
            writer.writerow([row.t_s, row.x_m, row.y_m, row.z_m])

    loaded = load_pose_csv(csv_path)
    summary = analyze_controlled_r(loaded)
    json_out = tmp_path / "noise_summary.json"
    md_out = tmp_path / "noise_summary.md"
    write_outputs(summary, json_out, md_out)

    persisted = json.loads(json_out.read_text(encoding="utf-8"))
    markdown = md_out.read_text(encoding="utf-8")
    assert persisted["primary_r_source"] == "RAW_RESIDUAL_COVARIANCE_FIXED_15_75"
    assert "15-35" in markdown
    assert "35-55" in markdown
    assert "55-75" in markdown
    assert "does not validate tracker accuracy" in markdown.lower()
