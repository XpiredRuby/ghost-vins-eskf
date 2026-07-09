# GHOST Software-Regime Runbook

This runbook is intentionally no-hardware.

Do **not** use the Raspberry Pi, camera, live AprilTag feed, or ROS runtime for this validation step.

## Validation status

This is a **candidate placeholder harness**, not final report-grade validation.

The generated `summary.md`, `summary.json`, and `replay.html` now carry this caveat directly:

```text
CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
```

Do not cite a `PASS` from this harness as proof of real-world tracker correctness until the hardware-calibrated noise thresholds and acceptance gates are committed, reviewed, and traced to the design report.

## Purpose

This validates the part of GHOST that must be correct before live testing resumes:

```text
visible stationary target -> visual occlusion -> no fake dominant motion
```

The accepted behavior is:

```text
HIDDEN - STATIONARY HOLD
rank 1 hypothesis = stationary_hold
rank 1 relative hypothesis weight >= 0.90
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
8 passed
```

Expected acceptance harness result:

```text
Overall: PASS
Scenarios: 7/7 passing
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

| Scenario | Purpose | Caveat |
|---|---|---|
| stationary_hide_reveal | Proves stationary occlusion does not create fake dominant motion | Synthetic white measurement noise |
| stationary_colored_noise_hide_reveal | Adds synthetic autocorrelated AR(1) drift to the stationary occlusion case | Not yet real Allan/PSD replay |
| constant_velocity_hide_reveal | Proves a moving target is not wrongly locked stationary | Synthetic trajectory |
| move_then_stop_behind_wall | Checks stop/hover plausibility under occlusion | Top-3 gate is a candidate requirement |
| lateral_hidden_motion | Checks that top-3 futures keep lateral motion plausible | Top-3 gate is a candidate requirement |
| long_occlusion_reset | Forces V1 to admit unknown/reset after a long hide | Synthetic long-hide case |
| single_outlier_white_noise | Checks visible-state response to one deterministic outlier plus white noise | Not a general false-measurement or colored-noise robustness claim |

## Threshold provenance

Current stationary speed thresholds:

```text
stationary_window_s = 1.5
stationary_enter_speed_mps = 0.065
stationary_exit_speed_mps = 0.090
```

These values reflect the empirical stationary-noise range discussed during the prior analysis session:

```text
~0.065 m/s at 1.5 s window
~0.09 m/s at 1.0 s window
```

They are still marked as candidate values until a hardware noise-calibration artifact is committed into the repo.

Current pass/fail gates such as:

```text
stationary_false_motion_limit_mps = 0.01
stop_wall_top3_limit_m = 0.40
lateral_top3_limit_m = 0.60
visible_rmse_limit_m = 0.10
```

are explicit V1 engineering requirements/placeholders. They are no longer hidden magic numbers, but they still need formal traceability to the design report before being used as report-grade validation evidence.

## Metrics that matter most

| Metric | Why it matters |
|---|---|
| stationary_false_motion_mps | Detects fake motion during stationary occlusion |
| top1_model_at_first_hidden | Must be `stationary_hold` in the stationary case |
| top1_relative_hypothesis_weight_at_first_hidden | Must be >= 0.90 in the stationary case |
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

This harness can support Pi work resuming as integration work, but it is not itself final validation.

Before citing its PASS result in a report, close these items:

```text
1. Commit hardware-calibrated noise/Allan/PSD replay data or parameter file.
2. Trace each acceptance gate to a stated requirement.
3. Replace synthetic AR(1) drift with measured colored-noise replay or clearly keep it labeled synthetic.
4. Port reviewed stationary-hold behavior into the live ROS tracker in a separate PR.
```
