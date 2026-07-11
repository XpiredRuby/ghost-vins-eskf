import math
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.statistical_comparison import paired_comparison  # noqa: E402


def test_paired_comparison_known_effect():
    result = paired_comparison(
        [0.10, 0.12, 0.11, 0.13],
        [0.05, 0.07, 0.06, 0.08],
        "known_effect",
        n_boot=200,
        seed=7,
    )

    assert result["condition"] == "known_effect"
    assert result["n_trials"] == 4
    assert math.isclose(result["median_error_difference_mh_minus_imm"], -0.05)
    assert math.isclose(result["median_error_reduction_mh_vs_imm"], 0.05)
    ci = result["bootstrap_ci_95_mh_minus_imm"]
    assert ci["high"] < 0.0


def test_paired_comparison_all_zero_edge_case():
    result = paired_comparison([0.1, 0.2, 0.3], [0.1, 0.2, 0.3], "all_zero", n_boot=50)

    assert result["median_error_difference_mh_minus_imm"] == 0.0
    assert result["median_error_reduction_mh_vs_imm"] == 0.0
    assert result["bootstrap_ci_95_mh_minus_imm"]["low"] == 0.0
    assert result["bootstrap_ci_95_mh_minus_imm"]["high"] == 0.0
    if result["wilcoxon_available"]:
        assert result["wilcoxon_p_value"] == 1.0


def test_paired_comparison_noisy_null_effect_spans_zero():
    imm = [0.20] * 10
    paired_differences = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05]
    mh = [imm_value + difference for imm_value, difference in zip(imm, paired_differences)]

    result = paired_comparison(
        imm,
        mh,
        "noisy_null",
        n_boot=4000,
        seed=260710,
    )

    assert result["n_trials"] == 10
    assert result["median_error_difference_mh_minus_imm"] == pytest.approx(0.0, abs=1e-12)
    assert result["median_error_reduction_mh_vs_imm"] == pytest.approx(0.0, abs=1e-12)
    ci = result["bootstrap_ci_95_mh_minus_imm"]
    assert ci["low"] < 0.0 < ci["high"]
    if result["wilcoxon_available"]:
        assert result["wilcoxon_p_value"] > 0.5


def test_paired_comparison_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="equal length"):
        paired_comparison([0.1, 0.2], [0.1], "bad")


def test_paired_comparison_bootstrap_is_deterministic_with_seed():
    kwargs = {"condition_name": "seeded", "n_boot": 100, "seed": 42}
    first = paired_comparison([0.3, 0.2, 0.4], [0.2, 0.25, 0.3], **kwargs)
    second = paired_comparison([0.3, 0.2, 0.4], [0.2, 0.25, 0.3], **kwargs)

    assert first["bootstrap_ci_95_mh_minus_imm"] == second["bootstrap_ci_95_mh_minus_imm"]
