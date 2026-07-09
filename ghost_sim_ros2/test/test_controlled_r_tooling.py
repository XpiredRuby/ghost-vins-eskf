import csv
import json
import math
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from tools.export_vision_pose_csv import export_input
from tools.make_stationary_noise_summary import write_summary


def test_export_vision_pose_jsonl_to_csv(tmp_path: Path):
    jsonl = tmp_path / "vision_pose.jsonl"
    rows = [
        {"t_rel_s": 0.0, "position": {"x_m": 1.0, "y_m": 2.0, "z_m": 3.0}},
        {"t_rel_s": 0.1, "position": {"x_m": 1.1, "y_m": 2.1, "z_m": 3.1}},
        {"t_rel_s": 0.2, "position": {"x_m": 1.2, "y_m": 2.2, "z_m": 3.2}},
    ]
    jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    out = tmp_path / "vision_pose_log.csv"

    count = export_input(jsonl, out)

    assert count == 3
    with out.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["t", "x", "y", "z"]
        got = list(reader)
    assert got[0] == {"t": "0.000000000", "x": "1.000000000", "y": "2.000000000", "z": "3.000000000"}
    assert got[-1] == {"t": "0.200000000", "x": "1.200000000", "y": "2.200000000", "z": "3.200000000"}


def test_make_stationary_noise_summary_outputs_json_and_markdown(tmp_path: Path):
    csv_path = tmp_path / "vision_pose_log.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "x", "y", "z"])
        for i in range(96):
            t = i * 0.05
            x = 0.5 + 0.001 * math.sin(i * 0.2)
            y = -0.2 + 0.0015 * math.cos(i * 0.17)
            z = 1.0 + 0.0005 * math.sin(i * 0.11)
            writer.writerow([f"{t:.3f}", f"{x:.9f}", f"{y:.9f}", f"{z:.9f}"])

    json_out = tmp_path / "noise_summary.json"
    md_out = tmp_path / "noise_summary.md"
    summary = write_summary(csv_path, json_out, md_out, include_detrended_r=True)

    assert json_out.exists()
    assert md_out.exists()
    loaded = json.loads(json_out.read_text(encoding="utf-8"))
    assert loaded["source_csv"] == str(csv_path)
    assert loaded["empirical_raw_r"]["dimensions"] == ["x", "y"]
    assert loaded["empirical_raw_r"]["sample_mode"] == "raw"
    assert loaded["status_labels"]["estimator_accuracy_status"] == "DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY"
    assert "detrended_diagnostic_r" in loaded
    assert summary["empirical_raw_r"]["sample_count"] > 8

    md = md_out.read_text(encoding="utf-8")
    assert "## Stationary AprilTag Noise Characterization" in md
    assert "## Recommended empirical raw R_xy" in md
    assert "raw R may include colored/drift components" in md
    assert "## Detrended diagnostic R_xy" in md
