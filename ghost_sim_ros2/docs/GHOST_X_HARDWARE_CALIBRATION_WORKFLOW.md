# GHOST-X Hardware Calibration and Frozen Validation Workflow

## Baseline

The immutable pre-hardware software baseline is:

- tag: `ghost-x-software-v1`
- commit: `4dbf5a86bcb5f8d84890173bfab76705b84ad128`
- development branch for hardware-informed changes: `ghost-x-hardware-calibration`

The tag must never move. Hardware-derived corrections are committed only to the calibration branch.

## Collection rule

Formal physical collection is performed without changing estimator parameters, covariance models, gates, priors, timing assumptions, or trial acceptance rules between trials. Failed and invalid trials remain in the campaign with explicit reasons.

## Predeclared data partition

### G3 stationary measurement characterization

Each of the nine range/yaw conditions has two repeats:

- repeat 1: calibration set
- repeat 2: frozen validation set

The calibration set may be used to select a measurement covariance model and estimate bias. The frozen validation set is evaluated only after the model and parameters are locked.

### G4 physical controlled truth

The physical trajectory campaign mirrors the eight declared scenario families with three repeats per family:

- repeats 1 and 2: calibration set
- repeat 3: frozen validation set

This produces 16 calibration trials and 8 frozen validation trials, with a minimum of 20 accepted paired trials required across the full 24-trial campaign. Invalid and failed trials are retained rather than replaced silently.

## Hardware-informed change process

1. Collect the complete predeclared campaign using the frozen software release and protocol.
2. Analyze only the calibration partition.
3. Record every discrepancy between the pre-hardware assumptions and measured behavior.
4. Modify software only on `ghost-x-hardware-calibration`.
5. Rerun Python, C++, ROS, replay, fault, equivalence, and CI gates.
6. Freeze a hardware-calibrated release candidate.
7. Evaluate the untouched validation partition once.
8. Publish `ghost-x-validated-v1` only if the evidence supports the claims; otherwise retain failures and narrow the claims.

## Reproduction

```bash
python3 ghost_sim_ros2/tools/init_ghost_x_hardware_calibration.py \
  --plan ghost_sim_ros2/config/ghost_x_hardware_calibration_plan.yaml \
  --g3-trial-order /home/xpired/ghost_trials/ghost_x_g3_measurement_v1/trial_order.csv \
  --out-dir /home/xpired/ghost_trials/ghost_x_hardware_calibration_v1 \
  --repo-root /home/xpired/ghost_ws/src/ghost-vins-eskf
```

The generated partition manifest is hash-protected and must be retained with the physical evidence.

## Claim boundary

This workflow establishes experiment governance and prevents calibration/validation leakage. It does not itself establish physical accuracy, estimator superiority, hard real-time behavior, flight qualification, or autonomous-flight readiness.
