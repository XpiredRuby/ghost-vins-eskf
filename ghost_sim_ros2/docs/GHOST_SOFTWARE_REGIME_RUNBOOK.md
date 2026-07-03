# GHOST Software-Regime Runbook

This runbook is intentionally no-hardware.

Do **not** use the Raspberry Pi, camera, live AprilTag feed, or ROS runtime for this validation step.

## Purpose

This validates the part of GHOST that must be correct before live testing resumes:

```text
visible stationary target -> visual occlusion -> no fake dominant motion
```

The accepted behavior is:

```text
HIDDEN - STATIONARY HOLD
rank 1 hypothesis = stationary_hold
rank 1 probability >= 0.90
dominant future path stays at last measured position
uncertainty grows with occlusion age
```

## Commands

From the repository root:

```bash
python ghost_sim_ros2/analysis/ghost_software_regime.py --out ghost_regime_runs/latest
pytest -q ghost_sim_ros2/test/test_ghost_software_regime.py
```

Expected focused pytest result:

```text
3 passed
```

Expected acceptance harness result:

```text
Overall: PASS
Scenarios: 6/6 passing
```

## Generated outputs

The harness generates:

```text
ghost_regime_runs/latest/summary.md
ghost_regime_runs/latest/summary.json
ghost_regime_runs/latest/replay.html
ghost_regime_runs/latest/<scenario>/measurements.csv
ghost_regime_runs/latest/<scenario>/futures.jsonl
ghost_regime_runs/latest/<scenario>/metrics.json
```

## Scenarios

| Scenario | Purpose |
|---|---|
| stationary_hide_reveal | Proves stationary occlusion does not create fake motion |
| constant_velocity_hide_reveal | Proves a moving target is not wrongly locked stationary |
| move_then_stop_behind_wall | Checks stop/hover plausibility under occlusion |
| lateral_hidden_motion | Checks that top-3 futures keep lateral motion plausible |
| long_occlusion_reset | Forces V1 to admit unknown/reset after a long hide |
| false_measurement_jump | Checks visible-state robustness to one bad measurement |

## Metrics that matter most

| Metric | Why it matters |
|---|---|
| stationary_false_motion_mps | Detects fake motion during stationary occlusion |
| top1_model_at_first_hidden | Must be `stationary_hold` in the stationary case |
| top1_probability_at_first_hidden | Must be >= 0.90 in the stationary case |
| top3_best_terminal_error_m | Measures whether the hypothesis bank contains a plausible future |
| reset_count | Ensures V1 does not claim indefinite hidden tracking |

## Claim discipline

Safe claim:

> GHOST V1 is a calibrated vision-only AprilTag occlusion tracker with a heuristic multi-hypothesis motion bank. During occlusion, it ranks plausible futures and explicitly distinguishes measurement from prediction.

Unsafe claim:

> GHOST sees or measures the hidden target.

Unsafe claim:

> GHOST uses formal IMM/MHT/ESKF/VINS.

That terminology is reserved for future versions after formal probability recursion and/or IMU fusion are implemented.

## Pi gate

The Pi stays frozen until these pass in GitHub:

```text
python ghost_sim_ros2/analysis/ghost_software_regime.py --out ghost_regime_runs/latest
pytest -q ghost_sim_ros2/test/test_ghost_software_regime.py
```

Once both pass, Pi integration can resume only as an integration test, not as the place where the core tracker logic is debugged.
