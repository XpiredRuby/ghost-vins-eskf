# GHOST Live Tracker Stationary-Hold Integration

This document covers the live ROS tracker integration of the software-regime stationary-hold behavior.

## Scope

This PR ports reviewed scaffold behavior into the live ROS wrapper only.

It does **not** claim final hardware validation.

## What changed

The live `mh_tracker.py` stationary gate now uses the same reviewed candidate thresholds as the offline software-regime harness:

```text
stationary_window_s = 1.5
stationary_enter_speed_mps = 0.065
stationary_exit_speed_mps = 0.090
stationary_hold_prior = 0.95
stationary_hold_max_s = 4.0
```

`stationary_hold_prior = 0.95` is also a candidate V1 design prior, not a measured probability. It is carried in the live payload with its own status/provenance fields so it does not become an undocumented magic number.

When the target was stationary before measurement loss, the live wrapper:

```text
1. marks hidden_stationary_hold_active = true
2. publishes odometry at the last visible position
3. publishes zero output velocity
4. suppresses dynamic hidden-motion futures
5. emits rank-1 stationary_hold in /ghost/tracker_mh/futures_json
6. emits status text: HIDDEN - STATIONARY HOLD
```

## Important implementation notes

The live wrapper rejects `x < 0.0` detections because V1 treats camera-frame `+x` as forward range. Negative `x` is behind the camera/invalid for the current single-camera bench geometry. Lateral `y` may be positive or negative.

The stationary gate updates only on real visible pose messages. During occlusion there are no new poses, so the gate state intentionally freezes at the last visible decision. This preserves the answer to: "was the target stationary immediately before hiding?" The separate `stationary_hold_max_s` bound prevents holding that belief forever.

## Payload caveat

The live futures payload now carries:

```text
stationary_threshold_status
stationary_threshold_provenance
stationary_window_s
stationary_enter_speed_mps
stationary_exit_speed_mps
stationary_hold_prior
stationary_hold_prior_status
stationary_hold_prior_provenance
stationary_hold_max_s
```

The status string is:

```text
CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
```

This caveat must remain visible until hardware-calibrated noise thresholds are committed and reviewed.

## No Pi gate

This integration PR is still software-side.

Do not treat merge as live hardware validation.

Before using this as report-grade evidence, close:

```text
1. Hardware noise replay or calibration artifact committed into repo.
2. Live ROS trial logs showing stationary hide/reveal behavior.
3. Dashboard confirms stationary_hold rank 1 while hidden.
4. Engineer review of live tracker PR.
```

## Local software tests

Pure Python tests:

```bash
pytest -q ghost_sim_ros2/test/test_stationary_gate.py
```

Full software-regime workflow:

```bash
python ghost_sim_ros2/analysis/ghost_software_regime.py --out ghost_regime_runs/latest
pytest -q ghost_sim_ros2/test/test_ghost_software_regime.py ghost_sim_ros2/test/test_stationary_gate.py
```

## Live ROS test later

Only after review, on Pi:

```bash
ros2 run ghost_sim_ros2 mh_tracker --ros-args \
  -p stationary_gate_enabled:=true \
  -p stationary_enter_speed_mps:=0.065 \
  -p stationary_exit_speed_mps:=0.090
```

Expected hidden stationary payload behavior:

```json
{
  "hidden_stationary_hold_active": true,
  "stationary_hold_prior": 0.95,
  "stationary_hold_prior_status": "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R",
  "hypotheses": [
    {
      "rank": 1,
      "model": "stationary_hold",
      "probability": 0.95,
      "vx_mps": 0.0,
      "vy_mps": 0.0
    }
  ]
}
```
