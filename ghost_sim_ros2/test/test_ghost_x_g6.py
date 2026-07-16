from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from analysis.ghost_x_consistency import (
    analyze_campaign,
    quadratic_form,
    residual_diagnostics,
    summarize_quadratic,
)


def test_quadratic_form_and_bounds() -> None:
    value = quadratic_form([1.0, 2.0], [[2.0, 0.0], [0.0, 4.0]])
    assert value is not None
    assert math.isclose(value, 1.5, rel_tol=0.0, abs_tol=1e-12)
    summary = summarize_quadratic("NIS", [1.0, 2.0, 3.0], 2)
    assert summary.count == 3
    assert summary.mean == 2.0
    assert summary.mean_bounds_95 is not None


def test_quadratic_form_rejects_singular_covariance() -> None:
    assert quadratic_form([1.0, 0.0], [[1.0, 0.0], [0.0, 0.0]]) is None


def test_residual_diagnostics() -> None:
    rng = np.random.default_rng(7)
    residuals = rng.normal(0.0, 1.0, size=(200, 2)).tolist()
    result = residual_diagnostics(residuals, max_lag=10)
    assert result["valid"] is True
    assert len(result["dimensions"]) == 2
    assert all(item["count"] == 200 for item in result["dimensions"])


def test_full_canonical_campaign_if_present() -> None:
    campaign = Path("/home/xpired/ghost_trials/ghost_x_g4_controlled_truth_v1")
    if not campaign.is_dir():
        return
    report = analyze_campaign(campaign)
    assert report["canonical_trials"] == 24
    assert report["pooled"]["cv"]["nis"]["count"] > 1000
    assert report["pooled"]["formal_imm"]["nis_validity"].startswith("APPROXIMATE")
    assert report["pooled"]["ghost_mh"]["nis"]["valid"] is False
    assert len(report["covariance_sensitivity"]) == 3
