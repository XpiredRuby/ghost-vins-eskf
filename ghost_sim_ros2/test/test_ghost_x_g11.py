from __future__ import annotations

from pathlib import Path

import numpy as np

from analysis.ghost_x_fixed_lag import (
    apply_ood,
    fixed_lag_smooth,
    load_config,
    load_streams,
    paired_bootstrap,
    select_candidate,
)


def test_fixed_lag_returns_delayed_outputs() -> None:
    rows = []
    for index in range(20):
        rows.append(
            {
                "dt_s": 0.1,
                "t_s": 0.1 * index,
                "visible": True,
                "measurement_xy_m": [0.1 * index, 0.0],
                "measurement_covariance_xy_m2": [[1.0e-4, 0.0], [0.0, 1.0e-4]],
                "truth": {"x_m": 0.1 * index, "y_m": 0.0, "vx_mps": 1.0, "vy_mps": 0.0},
            }
        )
    result = fixed_lag_smooth(rows, lag_steps=5, acceleration_std_mps2=0.65)
    assert min(result["outputs"]) == 0
    assert max(result["outputs"]) == 14
    assert all(output["effective_lag_steps"] == 5 for output in result["outputs"].values())
    assert all(np.isfinite(output["state"]).all() for output in result["outputs"].values())


def test_ood_transform_is_deterministic() -> None:
    config = load_config(Path("config/ghost_x_g11_fixed_lag.yaml"))
    campaign = Path(str(config["source_campaign"]))
    if not campaign.is_dir():
        return
    stream = load_streams(campaign)[0]
    first = apply_ood(stream.rows, config["out_of_distribution"])
    second = apply_ood(stream.rows, config["out_of_distribution"])
    assert first == second


def test_selection_prefers_simpler_candidate_within_tie() -> None:
    results = [
        {"valid": True, "score": 1.0, "lag_steps": 20, "acceleration_std_mps2": 0.65, "compute_us_per_step": 20.0},
        {"valid": True, "score": 1.01, "lag_steps": 5, "acceleration_std_mps2": 0.65, "compute_us_per_step": 10.0},
    ]
    selected = select_candidate(results, 0.02)
    assert selected["lag_steps"] == 5


def test_paired_bootstrap_sign() -> None:
    baseline = {"a": 1.0, "b": 2.0, "c": 3.0}
    advanced = {"a": 0.8, "b": 1.8, "c": 2.8}
    report = paired_bootstrap(baseline, advanced, samples=200)
    assert report["n_trials"] == 3
    assert report["median_advanced_minus_baseline_m"] < 0.0
