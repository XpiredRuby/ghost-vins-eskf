import csv
import json
import math
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.grid_validation_analysis import analyze_grid  # noqa: E402


def test_grid_validation_analysis_computes_bias_rmse_and_outputs(tmp_path: Path):
    pose_log = tmp_path / "vision_pose.jsonl"
    grid_csv = tmp_path / "grid.csv"
    out_dir = tmp_path / "out"

    points = [
        ("p1", 0.0, 0.0, 0.0, 10.0),
        ("p2", 1.0, 0.0, 10.0, 20.0),
        ("p3", 1.0, 1.0, 20.0, 30.0),
    ]
    with grid_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["point_id", "x_true_m", "y_true_m", "t_start_s", "t_end_s"])
        writer.writerows(points)

    rows = []
    for _, x_true, y_true, t_start, _ in points:
        for i, jitter in enumerate([-0.01, 0.0, 0.01]):
            rows.append(
                {
                    "t_rel_s": t_start + 1.0 + i,
                    "position": {
                        "x_m": x_true + 0.02 + jitter,
                        "y_m": y_true - 0.01 - jitter,
                    },
                }
            )
    pose_log.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    summary = analyze_grid(pose_log, grid_csv, out_dir)

    assert math.isclose(summary["aggregate"]["bias_x_m"], 0.02, abs_tol=1e-12)
    assert math.isclose(summary["aggregate"]["bias_y_m"], -0.01, abs_tol=1e-12)
    assert math.isclose(summary["aggregate"]["rmse_m"], math.hypot(0.02, -0.01), abs_tol=1e-12)
    assert summary["points"][0]["n_samples"] == 3
    assert math.isclose(summary["points"][0]["x_std_m"], 0.01, abs_tol=1e-12)
    assert (out_dir / "grid_validation_summary.json").exists()
    assert (out_dir / "grid_validation_summary.md").exists()

    loaded = json.loads((out_dir / "grid_validation_summary.json").read_text(encoding="utf-8"))
    assert loaded["aggregate"]["mean_error_m"] == summary["aggregate"]["mean_error_m"]
    md = (out_dir / "grid_validation_summary.md").read_text(encoding="utf-8")
    assert "Ground Truth Grid Validation Summary" in md
    assert "initial accuracy evidence only" in md
