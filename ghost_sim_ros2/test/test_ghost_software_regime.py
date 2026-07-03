import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "analysis" / "ghost_software_regime.py"
    spec = importlib.util.spec_from_file_location("ghost_software_regime", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _score(name):
    mod = _load_module()
    cfg = mod.RegimeConfig()
    scenario = mod.make_scenarios()[name]
    measurements = mod.generate_measurements(scenario, cfg)
    outputs = mod.run_tracker(measurements, cfg)
    return mod.score_scenario(scenario, measurements, outputs)


def test_stationary_hidden_uses_stationary_hold():
    score = _score("stationary_hide_reveal")
    assert score.pass_fail == "PASS"
    assert score.top1_model_at_first_hidden == "stationary_hold"
    assert score.top1_probability_at_first_hidden >= 0.90
    assert score.stationary_false_motion_mps <= 0.01


def test_moving_target_not_locked_stationary():
    score = _score("constant_velocity_hide_reveal")
    assert score.pass_fail == "PASS"
    assert score.top1_model_at_first_hidden != "stationary_hold"


def test_long_occlusion_resets():
    score = _score("long_occlusion_reset")
    assert score.pass_fail == "PASS"
    assert score.reset_count > 0
