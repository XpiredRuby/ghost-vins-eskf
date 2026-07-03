import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.observability_crlb import (  # noqa: E402
    cv_position_crlb,
    cv_state_transition,
    format_markdown,
    linear_crlb,
    observability_report,
    position_measurement_matrix,
    range_bearing_jacobian_xy,
)


def test_cv_position_model_observable_after_two_steps():
    f = cv_state_transition(0.1)
    h = position_measurement_matrix()

    one_step = observability_report(f, h, horizon_steps=1)
    two_steps = observability_report(f, h, horizon_steps=2)

    assert one_step.rank == 2
    assert not one_step.observable
    assert two_steps.rank == 4
    assert two_steps.observable


def test_cv_position_crlb_improves_with_longer_horizon():
    _, short = cv_position_crlb(dt=0.1, position_std_m=0.05, horizon_steps=2)
    _, long = cv_position_crlb(dt=0.1, position_std_m=0.05, horizon_steps=8)

    assert not short.singular
    assert not long.singular
    assert np.trace(np.asarray(long.crlb_covariance)) < np.trace(np.asarray(short.crlb_covariance))
    assert long.std[0] < short.std[0]


def test_lower_measurement_noise_gives_lower_crlb():
    f = cv_state_transition(0.1)
    h = position_measurement_matrix()
    loose = linear_crlb(f, h, np.eye(2) * 0.10**2, horizon_steps=5)
    tight = linear_crlb(f, h, np.eye(2) * 0.02**2, horizon_steps=5)

    assert np.trace(np.asarray(tight.crlb_covariance)) < np.trace(np.asarray(loose.crlb_covariance))


def test_range_bearing_jacobian_xy_matches_reference_values():
    jacobian = range_bearing_jacobian_xy(3.0, 4.0)

    assert jacobian.shape == (2, 2)
    assert np.allclose(jacobian[0], [0.6, 0.8])
    assert np.allclose(jacobian[1], [-4.0 / 25.0, 3.0 / 25.0])


def test_range_bearing_jacobian_rejects_origin():
    try:
        range_bearing_jacobian_xy(0.0, 0.0)
    except ValueError as exc:
        assert "origin" in str(exc)
    else:
        raise AssertionError("origin should be singular")


def test_markdown_report_contains_core_fields():
    obs, crlb = cv_position_crlb(dt=0.05, position_std_m=0.05, horizon_steps=4)
    text = format_markdown(obs, crlb)

    assert "Observable" in text
    assert "CRLB standard deviations" in text
    assert str(obs.rank) in text
    assert all(math.isfinite(v) for v in crlb.std)
