# GHOST Formal Campaign Parameter Lock

## Purpose

Pin the estimator implementation, protocols, calibration, runtime-parameter snapshot and Git revision before formal campaign outcomes are reviewed.

## Boundary

```text
Lock proves: BYTE IDENTITY + GIT REVISION
Lock does not prove: CORRECT TUNING OR PHYSICAL VALIDITY
```

## Create the lock

First save live ROS parameter dumps and camera-control output into the campaign directory. Then run:

```bash
python3 ghost_sim_ros2/tools/parameter_lock.py create \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf \
  --out ~/ghost_trials/imm_mh_campaign_v1/parameter_lock.json \
  --external camera_calibration=~/ghost_camera_calibration.json \
  --external camera_controls=~/ghost_trials/imm_mh_campaign_v1/camera_controls_locked.txt \
  --runtime-parameters ~/ghost_trials/imm_mh_campaign_v1/ros_parameters_locked.yaml \
  --notes "Locked after six dry runs and before formal campaign collection."
```

By default the tool hashes the formal IMM and MH implementations, IMM core, measurement/grid/campaign protocols, manifest template and controlled-R helper. Additional repository files can be supplied with repeated `--repo-file` arguments.

## Verify before formal collection

```bash
python3 ghost_sim_ros2/tools/parameter_lock.py verify \
  --lock ~/ghost_trials/imm_mh_campaign_v1/parameter_lock.json \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf \
  --external camera_calibration=~/ghost_camera_calibration.json \
  --external camera_controls=~/ghost_trials/imm_mh_campaign_v1/camera_controls_locked.txt \
  --out ~/ghost_trials/imm_mh_campaign_v1/parameter_lock_verification_before.json
```

Repeat verification after collection and preserve both results.

## Lock contents

- Git HEAD and branch;
- Git working-tree status;
- repository-relative file labels, sizes and SHA-256;
- external local file labels, paths, sizes and SHA-256;
- runtime-parameter snapshot hash;
- UTC creation time;
- mutation rule and claims boundary.

The local calibration/control paths belong in the private evidence package. Public summaries should use labels and hashes rather than personal absolute paths.

## Change rule

A change to any locked item after formal collection begins requires:

1. stopping the current configuration block;
2. preserving all existing trials;
3. documenting the reason;
4. creating a new parameter lock and configuration ID;
5. preventing casual statistical pooling across configurations;
6. rerunning dry validation where the change can affect results.

Never update the lock file in place. It is intentionally non-overwriting.

## Test

```bash
PYTHONPATH=ghost_sim_ros2:ghost_sim_ros2/tools \
python3 -m pytest -q ghost_sim_ros2/test/test_parameter_claims_lock.py
```
