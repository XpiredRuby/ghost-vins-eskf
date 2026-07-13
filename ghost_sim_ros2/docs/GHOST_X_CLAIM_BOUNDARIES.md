# GHOST-X Claim Boundaries

This document controls public, résumé, portfolio, and technical-defense wording until later GHOST-X phases produce stronger evidence.

## Supported now

| Claim | Evidence |
|---|---|
| Built a ROS 2 camera-to-estimator pipeline on Raspberry Pi | Preserved USB-camera MCAP bag and hardware reports |
| Implemented formal IMM and GHOST multi-hypothesis trackers | Source, tests, live topics, hardware bag, deterministic replay |
| Continued publishing estimates and future hypotheses during camera measurement loss | Hardware representative trials and software mission evaluator |
| Demonstrated target reacquisition after visibility returned | Hardware representative trials and deterministic mission |
| Implemented a mobile observer simulation with obstacle-aware LOS, navigation, and reacquisition | `ghost_drone_mission.launch.py` and validation JSON |
| Collected an accepted stationary empirical measurement covariance artifact | `controlled_R_direct_01` fixed-window analysis |
| Built deterministic validation, automated metrics, dashboards, and regression tests | Repository tooling and 214-test regression result |

## Supported only with qualifiers

| Qualified claim | Required qualifier |
|---|---|
| “GPS-denied tracking” | Target state is estimated without GPS measurements; current software mission assumes a known local observer pose and map |
| “Autonomous navigation” | Deterministic local-frame software observer navigation, not real flight |
| “Hardware validated” | Camera-to-ROS-to-tracker behavior and representative occlusion/reacquisition are hardware exercised; physical trajectory accuracy is not yet independently validated |
| “Measurement covariance calibrated” | Empirical stationary covariance under one locked camera/target setup; whiteness and state dependence remain unproven |
| “Real time” | Nodes ran at measured rates, but deadline, jitter, CPU, memory, and thermal worst-case evidence remain pending G9 |
| “GHOST-MH outperformed IMM” | May be stated only for an explicitly named individual proxy or software scenario; no general superiority claim is supported |

## Not supported yet

Do not publicly claim any of the following until the mapped GHOST-X phase passes:

- physical position or velocity RMSE against independent truth;
- formal statistical superiority of GHOST-MH over IMM;
- a completed 55-trial physical campaign;
- complete controlled-truth validation;
- NIS or NEES consistency without valid assumptions and truth covariance;
- GPS-denied self-localization, visual-inertial odometry, or SLAM;
- PX4 integration;
- real drone command or autonomous flight;
- production robustness;
- safety-critical, certifiable, or flight-qualified readiness;
- general object tracking beyond the demonstrated AprilTag target proxy;
- calibrated probability interpretation for all GHOST-MH relative hypothesis weights;
- deadline-compliant real-time behavior under worst-case load.

## Upgrade gates

| Future public claim | Minimum gate |
|---|---|
| Physical tracking accuracy | G4 controlled truth with declared uncertainty |
| Estimator consistency | G6 NIS/NEES validity review |
| Parameter optimality | G7 predeclared trade study |
| Fault tolerance | G8 reproducible fault matrix |
| Real-time performance | G9 worst-case timing/resource evidence |
| Regression-hardened release | G10 canonical replay and CI bands |
| Hardware-validated autonomous platform | Physical observer or vehicle navigation test, not camera-only tracker behavior |
| 97/100 full-depth completion | All mandatory master-plan acceptance criteria |

## Current approved one-sentence description

> GHOST-X is a ROS 2 research platform for GPS-free target tracking and prediction through visibility loss, combining Raspberry Pi camera experiments with deterministic autonomous-observer simulation, formal IMM estimation, and multi-hypothesis future tracking.

## Current approved résumé wording

> Developed and hardware-exercised a Raspberry Pi/ROS 2 occlusion-aware tracking platform with formal IMM and multi-hypothesis estimators; built deterministic obstacle-aware observer simulation, automated replay metrics, and reacquisition validation while preserving explicit boundaries around physical accuracy and flight claims.
