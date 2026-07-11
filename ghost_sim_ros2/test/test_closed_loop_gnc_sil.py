import json
import math
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.closed_loop_gnc_sil import (  # noqa: E402
    SAFE_HOLD,
    ScenarioConfig,
    default_scenarios,
    run_scenario,
    write_suite_outputs,
)


def test_nominal_formal_imm_loop_reaches_bounded_standoff():
    result = run_scenario(default_scenarios()[0])
    summary = result.summary

    assert summary.finite_output is True
    assert summary.safe_hold_time_s == 0.0
    assert summary.final_standoff_error_m < 0.25
    assert summary.rms_standoff_error_after_5s_m < 0.40
    assert summary.minimum_separation_m > 0.75


def test_short_dropout_uses_prediction_and_reacquires_without_safe_hold():
    config = default_scenarios()[1]
    result = run_scenario(config)
    summary = result.summary

    assert math.isclose(summary.max_measurement_age_s, 1.5, abs_tol=config.dt_s)
    assert summary.safe_hold_time_s == 0.0
    assert summary.reacquisition_count == 1
    assert summary.max_command_acceleration_mps2 <= config.max_acceleration_mps2 + 1e-9
    assert any(sample["supervisor"] == "PREDICTION" for sample in result.samples)


def test_long_dropout_enters_safe_hold_and_keeps_commands_bounded():
    config = default_scenarios()[2]
    result = run_scenario(config)
    summary = result.summary

    assert summary.safe_hold_time_s >= 1.90
    assert summary.reacquisition_count == 1
    assert summary.max_command_acceleration_mps2 <= config.max_acceleration_mps2 + 1e-9
    assert summary.max_follower_speed_mps <= config.max_desired_speed_mps + 0.25
    assert any(sample["supervisor"] == SAFE_HOLD for sample in result.samples)


def test_closed_loop_scenario_is_deterministic_for_fixed_seed():
    config = ScenarioConfig(
        name="deterministic",
        duration_s=8.0,
        dropout_windows_s=((3.0, 4.0),),
        seed=42,
    )

    first = run_scenario(config)
    second = run_scenario(config)

    assert first.summary == second.summary
    assert first.samples == second.samples


def test_write_suite_outputs_creates_machine_and_human_readable_artifacts(tmp_path: Path):
    results = [run_scenario(config) for config in default_scenarios()]
    write_suite_outputs(results, tmp_path)

    json_path = tmp_path / "closed_loop_gnc_summary.json"
    md_path = tmp_path / "closed_loop_gnc_summary.md"
    assert json_path.exists()
    assert md_path.exists()

    summary = json.loads(json_path.read_text(encoding="utf-8"))
    assert summary["integration_status"] == "SOFTWARE_IN_THE_LOOP_ONLY"
    assert len(summary["scenarios"]) == 3
    assert "not PX4" in md_path.read_text(encoding="utf-8")
    for config in default_scenarios():
        assert (tmp_path / f"{config.name}.csv").exists()
