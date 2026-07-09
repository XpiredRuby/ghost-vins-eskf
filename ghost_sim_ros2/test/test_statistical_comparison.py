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


def test_paired_comparison_no_effect():
    result = paired_comparison([0.1, 0.2, 0.3], [0.1, 0.2, 0.3], "no_effect", n_boot=50)

    assert result["median_error_difference_mh_minus_imm"] == 0.0
    assert result["median_error_reduction_mh_vs_imm"] == 0.0
    assert result["bootstrap_ci_95_mh_minus_imm"]["low"] == 0.0
    assert result["bootstrap_ci_95_mh_minus_imm"]["high"] == 0.0


def test_paired_comparison_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="equal length"):
        paired_comparison([0.1, 0.2], [0.1], "bad")


def test_paired_comparison_bootstrap_is_deterministic_with_seed():
    kwargs = {"condition_name": "seeded", "n_boot": 100, "seed": 42}
    first = paired_comparison([0.3, 0.2, 0.4], [0.2, 0.25, 0.3], **kwargs)
    second = paired_comparison([0.3, 0.2, 0.4], [0.2, 0.25, 0.3], **kwargs)

    assert first["bootstrap_ci_95_mh_minus_imm"] == second["bootstrap_ci_95_mh_minus_imm"]
