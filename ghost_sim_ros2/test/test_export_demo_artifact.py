import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from tools.export_demo_artifact import export_demo_artifact  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_export_demo_artifact_writes_honest_downsampled_json(tmp_path: Path):
    _write_jsonl(
        tmp_path / "vision_pose.jsonl",
        [
            {"t_rel_s": 0.00, "position": {"x_m": 1.0, "y_m": 2.0}},
            {"t_rel_s": 0.05, "position": {"x_m": 1.1, "y_m": 2.1}},
            {"t_rel_s": 0.20, "position": {"x_m": 1.2, "y_m": 2.2}},
        ],
    )
    _write_jsonl(
        tmp_path / "imm_futures.jsonl",
        [{"t_rel_s": 0.00, "payload": {"visible": True, "estimate": {"x_m": 0.9, "y_m": 1.9}}}],
    )
    _write_jsonl(
        tmp_path / "mh_futures.jsonl",
        [
            {
                "t_rel_s": 0.00,
                "payload": {
                    "initialized": True,
                    "visible": False,
                    "hypotheses": [{"rank": 1, "model": "legacy", "probability": 0.75}],
                },
            }
        ],
    )
    _write_jsonl(tmp_path / "status.jsonl", [{"t_rel_s": 0.00, "status": "OCCLUDED - PREDICTING"}])

    out = tmp_path / "demo.json"
    artifact = export_demo_artifact(tmp_path, out, hz=10.0)

    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["metadata"]["demo_status"] == "integration_telemetry_demo"
    assert loaded["metadata"]["accuracy_validation_status"] == "pending_ground_truth_grid_validation"
    assert loaded == artifact
    assert len(loaded["frames"]) == 2
    first_hyp = loaded["frames"][0]["mh_hypotheses"][0]
    assert first_hyp["relative_hypothesis_weight"] == 0.75
    assert "probability" not in first_hyp
