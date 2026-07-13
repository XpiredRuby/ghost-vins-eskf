from analysis.ghost_mh_mode_bank import ModeBankTracker


def test_signed_local_coordinate_mode_retains_hidden_hypotheses():
    tracker = ModeBankTracker(
        max_occlusion_s=2.0,
        max_workspace_range_m=10.0,
        allow_signed_local_coordinates=True,
    )
    tracker.initialize([-3.0, 0.2], velocity_xy=[0.4, 0.0])
    tracker.was_visible = True
    tracker.step(0.1, None)
    assert tracker.initialized
    assert len(tracker.top_hypotheses()) > 0
    assert all(float(hyp.x[0, 0]) < 0.0 for hyp in tracker.top_hypotheses())


def test_hardware_default_still_rejects_hidden_negative_forward_state():
    tracker = ModeBankTracker(max_occlusion_s=2.0, max_workspace_range_m=10.0)
    tracker.initialize([-3.0, 0.2], velocity_xy=[0.4, 0.0])
    tracker.was_visible = True
    tracker.step(0.1, None)
    assert not tracker.initialized
