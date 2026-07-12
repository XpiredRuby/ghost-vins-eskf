import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.measurement_covariance_config import (  # noqa: E402
    CONTROLLED_R_CANDIDATE_DATASET,
    CONTROLLED_R_CANDIDATE_XY_M2,
    build_measurement_r_xy,
    covariance_to_list,
)


def test_scalar_fallback_produces_isotropic_diagonal():
    r = build_measurement_r_xy(0.005)
    assert r == ((2.5e-05, 0.0), (0.0, 2.5e-05))


def test_full_r_preserves_off_diagonal_sign():
    r = build_measurement_r_xy(0.005, 2.0e-6, -3.0e-7, 4.0e-6)
    assert r == ((2.0e-6, -3.0e-7), (-3.0e-7, 4.0e-6))
    assert covariance_to_list(r) == [[2.0e-6, -3.0e-7], [-3.0e-7, 4.0e-6]]


def test_non_psd_r_is_rejected():
    try:
        build_measurement_r_xy(0.005, 1.0e-6, 2.0e-6, 1.0e-6)
    except ValueError as exc:
        assert "positive semidefinite" in str(exc)
    else:
        raise AssertionError("non-PSD covariance should fail")


def test_nonfinite_r_is_rejected():
    try:
        build_measurement_r_xy(0.005, 1.0e-6, math.nan, 1.0e-6)
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("nonfinite covariance should fail")


def test_direct_controlled_r_candidate_is_exact_and_psd():
    expected = (
        (1.1285530537472441e-06, 9.517042606937477e-08),
        (9.517042606937477e-08, 1.396619108865118e-08),
    )
    assert CONTROLLED_R_CANDIDATE_XY_M2 == expected
    assert CONTROLLED_R_CANDIDATE_DATASET == "controlled_R_direct_01_fixed_15_75_s_n885"
    assert np.linalg.eigvalsh(np.asarray(expected)).min() > 0.0
