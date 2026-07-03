import importlib.util
import math
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "analysis" / "ghost_software_regime.py"
    spec = importlib.util.spec_from_file_location("ghost_software_regime", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _score(name):
    mod = _load_module()
    cfg = mod.RegimeConfig()
    scenario = mod.make_scenarios()[name]
    measurements = mod.generate_measurements(scenario, cfg)
    outputs = mod.run_tracker(measurements, cfg)
    return mod.score_scenario(scenario, measurements, outputs, cfg)


def test_all_scenarios_have_enforced_pass_gates():
    mod = _load_module()
    cfg = mod.RegimeConfig()
    for name, scenario in mod.make_scenarios().items():
        measurements = mod.generate_measurements(scenario, cfg)
        outputs = mod.run_tracker(measurements, cfg)
        score = mod.score_scenario(scenario, measurements, outputs, cfg)
        assert score.pass_fail == "PASS", f"{name}: {score.notes}"


def test_stationary_hidden_uses_stationary_hold():
    cfg = _load_module().RegimeConfig()
    score = _score("stationary_hide_reveal")
    assert score.top1_model_at_first_hidden == "stationary_hold"
    assert score.top1_probability_at_first_hidden >= cfg.stationary_prior_min
    assert score.stationary_false_motion_mps <= cfg.stationary_false_motion_limit_mps
    assert score.stationary_hold_fraction_hidden >= cfg.stationary_hold_fraction_min


def test_colored_noise_stationary_case_is_labeled_and_limited():
    cfg = _load_module().RegimeConfig()
    score = _score("stationary_colored_noise_hide_reveal")
    assert score.top1_model_at_first_hidden == "stationary_hold"
    assert score.stationary_false_motion_mps <= cfg.stationary_false_motion_limit_mps
    assert score.stationary_hold_fraction_hidden >= cfg.colored_noise_stationary_hold_fraction_min
    assert score.threshold_status == "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"


def test_moving_target_not_locked_stationary():
    score = _score("constant_velocity_hide_reveal")
    assert score.top1_model_at_first_hidden != "stationary_hold"


def test_move_then_stop_gate_is_ci_enforced():
    cfg = _load_module().RegimeConfig()
    score = _score("move_then_stop_behind_wall")
    assert score.top3_best_terminal_error_m <= cfg.stop_wall_top3_limit_m


def test_lateral_hidden_motion_gate_is_ci_enforced():
    cfg = _load_module().RegimeConfig()
    score = _score("lateral_hidden_motion")
    assert score.top3_best_terminal_error_m <= cfg.lateral_top3_limit_m


def test_long_occlusion_resets():
    score = _score("long_occlusion_reset")
    assert score.reset_count > 0


def test_single_outlier_white_noise_is_explicitly_scoped():
    cfg = _load_module().RegimeConfig()
    score = _score("single_outlier_white_noise")
    assert score.rmse_m <= cfg.visible_rmse_limit_m
    assert score.top1_model_at_first_hidden == "NONE"
    assert math.isnan(score.top1_terminal_error_m)
