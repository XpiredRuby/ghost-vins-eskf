from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = PACKAGE_ROOT / "tools" / "init_ghost_x_hardware_calibration.py"
SPEC = importlib.util.spec_from_file_location("ghost_x_hardware_calibration", TOOL_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load_plan() -> dict:
    return yaml.safe_load(
        (PACKAGE_ROOT / "config" / "ghost_x_hardware_calibration_plan.yaml").read_text(encoding="utf-8")
    )


def test_g4_partition_is_disjoint_and_complete() -> None:
    rows = MODULE.g4_rows(load_plan())
    assert len(rows) == 24
    assert sum(row["role"] == "calibration" for row in rows) == 16
    assert sum(row["role"] == "frozen_validation" for row in rows) == 8
    assert len({row["trial_id"] for row in rows}) == 24
    for family in {row["scenario_family"] for row in rows}:
        family_rows = [row for row in rows if row["scenario_family"] == family]
        assert [row["role"] for row in family_rows] == ["calibration", "calibration", "frozen_validation"]


def test_g3_partition_uses_repeat_one_for_calibration_and_two_for_validation(tmp_path: Path) -> None:
    path = tmp_path / "trial_order.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["sequence", "trial_id", "range_m", "yaw_deg", "repeat"],
        )
        writer.writeheader()
        sequence = 0
        for range_m in (0.70, 1.05, 1.40):
            for yaw_deg in (-20.0, 0.0, 20.0):
                for repeat in (1, 2):
                    sequence += 1
                    writer.writerow(
                        {
                            "sequence": sequence,
                            "trial_id": f"trial_{sequence:02d}",
                            "range_m": range_m,
                            "yaw_deg": yaw_deg,
                            "repeat": repeat,
                        }
                    )
    rows = MODULE.g3_rows(path, load_plan())
    assert len(rows) == 18
    assert sum(row["role"] == "calibration" for row in rows) == 9
    assert sum(row["role"] == "frozen_validation" for row in rows) == 9
    assert all(
        row["role"] == ("calibration" if row["repeat"] == 1 else "frozen_validation")
        for row in rows
    )


def test_partition_hash_is_deterministic() -> None:
    rows = MODULE.g4_rows(load_plan())
    payload = {"g4_trials": rows}
    assert MODULE.stable_hash(payload) == MODULE.stable_hash(payload)
    changed = {"g4_trials": [*rows[:-1], {**rows[-1], "role": "calibration"}]}
    assert MODULE.stable_hash(payload) != MODULE.stable_hash(changed)
