from types import SimpleNamespace

from analysis.ghost_offline_tracker_sweep import run_trial


def test_offline_trial_runs():
    args = SimpleNamespace(
        duration=3.0,
        rate=20.0,
        noise_std=0.025,
        dropout_start=1.0,
        dropout_duration=0.5,
        seed=7,
    )
    result = run_trial(args, accel_std=1.4, meas_std=0.08, gate_chi2=9.210)
    assert result.rms_error_m >= 0.0
    assert result.accepted > 0
