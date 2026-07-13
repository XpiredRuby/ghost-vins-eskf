from __future__ import annotations

from pathlib import Path

from analysis.ghost_x_trade_study import (
    choose_horizon,
    imm_candidates,
    load_design,
    mh_candidates,
    select_candidate,
)


def test_candidate_design_counts_and_balance() -> None:
    design = load_design(Path("config/ghost_x_g7_trade_study.yaml"))
    assert len(imm_candidates(design)) == 36
    mh = mh_candidates(design)
    assert len(mh) == 27
    assert len({tuple(sorted(item.items())) for item in mh}) == 27
    for field in ("model_count", "gate_chi2", "max_occlusion_s", "stationary_prior_scale"):
        counts = {}
        for item in mh:
            counts[item[field]] = counts.get(item[field], 0) + 1
        assert sorted(counts.values()) == [9, 9, 9]


def test_simpler_model_tie_rule() -> None:
    results = [
        {"valid": True, "score": 1.0, "compute_us_per_step": 20.0, "candidate": {"model_count": 8}},
        {"valid": True, "score": 1.015, "compute_us_per_step": 10.0, "candidate": {"model_count": 3}},
        {"valid": False, "score": 0.5, "compute_us_per_step": 1.0, "candidate": {"model_count": 1}},
    ]
    selected = select_candidate(results, 0.02, lambda candidate: (candidate["model_count"],))
    assert selected["candidate"]["model_count"] == 3


def test_horizon_selection_prefers_largest_acceptable() -> None:
    def evaluator(candidate):
        horizon = candidate["future_horizon_s"]
        return {"valid": True, "future_rmse_m": 0.2 * horizon, "candidate": candidate}

    selected, results = choose_horizon({"x": 1}, [0.5, 1.0, 1.5], evaluator, 0.25)
    assert len(results) == 3
    assert selected["candidate"]["future_horizon_s"] == 1.0
