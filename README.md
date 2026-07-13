# GHOST — GPS-Denied Hardware Occlusion-Survivable Tracker

[![GHOST CI](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/ci.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/ci.yml)
[![Closed-Loop GNC SIL](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/closed-loop-gnc-sil.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/closed-loop-gnc-sil.yml)
[![Campaign Analysis](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/campaign-analysis.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/campaign-analysis.yml)
[![Physical Session Readiness](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/physical-session-readiness.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/physical-session-readiness.yml)
![ROS 2 Jazzy](https://img.shields.io/badge/ROS%202-Jazzy-22314E)
![Sensor](https://img.shields.io/badge/sensor-USB%20UVC%20webcam-2ea44f)
![Validation](https://img.shields.io/badge/physical%20accuracy-pending-f59e0b)

**Hardware-integrated ROS 2 target-state estimation for intermittent vision, plus deterministic formal-IMM software-in-the-loop guidance and control.**

GHOST uses a **standard USB UVC webcam** connected to a Raspberry Pi through USB/V4L2—not a CSI camera. Calibrated AprilTag pose measurements drive a formal Interacting Multiple Model (IMM) estimator and a bounded heuristic multi-hypothesis (GHOST-MH) comparison tracker. The project exposes measurement age, prediction-only behavior, covariance, IMM mode probabilities, MH relative hypothesis weights, degraded-dropout state and reacquisition through ROS 2 telemetry and replayable evidence.

A separate deterministic software-in-the-loop harness connects the same formal IMM to relative-standoff guidance, acceleration-limited control, actuator lag, follower dynamics and a long-dropout safe-hold supervisor.

**Author:** Vinayak Manoj Nair — Texas A&M University, B.S. Aerospace Engineering, December 2026

> **Evidence boundary:** the preserved hardware run validates the USB-camera-to-ROS-to-tracker pipeline, real-time publication, dropout-state telemetry and replay. The closed-loop GNC results are deterministic software-in-the-loop evidence using synthetic truth and candidate noise parameters. Controlled measurement covariance, physical ground-truth accuracy, paired hardware superiority, vehicle control and flight readiness are not yet validated.

## Complete drone/robot mission demo

GHOST now includes the full intended software mission: a mobile drone/robot-style observer tracks a moving target in a local GPS-denied map, loses camera line of sight behind buildings, continues formal IMM and GHOST-MH prediction, navigates to a collision-free obstacle-corner vantage point, and reacquires the target.

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
source install/setup.bash
ros2 launch ghost_sim_ros2 ghost_drone_mission.launch.py
```

Dashboard: `http://<RASPBERRY_PI_IP>:8088`

Final deterministic mission result: **PASS** — two obstacle-caused LOS losses, `456` IMM and `457` GHOST-MH hidden outputs, two reacquisitions, `12.30 m` observer travel, and zero collisions or boundary violations.

- [Mission architecture and run guide](ghost_sim_ros2/docs/GHOST_DRONE_MISSION_SOFTWARE.md)
- [Final implementation report](ghost_sim_ros2/docs/GHOST_DRONE_MISSION_IMPLEMENTATION_REPORT.md)
- [Machine-readable mission evidence](ghost_sim_ros2/docs/GHOST_DRONE_MISSION_VALIDATION.json)

This demonstrates local-frame target estimation, prediction, guidance, and reacquisition. It does not claim SLAM/VIO, GPS-denied self-localization, PX4 integration, or real autonomous flight.

## Review GHOST in 60 seconds

1. Open the [public GHOST showcase](https://xpiredruby.github.io/ghost-vins-eskf/).
2. Launch the [interactive hardware replay](https://xpiredruby.github.io/ghost-vins-eskf/demo.html).
3. Explore the [USB hardware architecture and BOM](https://xpiredruby.github.io/ghost-vins-eskf/hardware.html).
4. Review the [portfolio packet](ghost_sim_ros2/docs/GHOST_PORTFOLIO_PACKET.md) and [full project report](ghost_sim_ros2/docs/GHOST_PROJECT_REPORT.md).
5. Inspect the [closed-loop GNC SIL](ghost_sim_ros2/docs/GHOST_CLOSED_LOOP_GNC_SIL.md).
6. Audit the [master physical-validation runbook](ghost_sim_ros2/docs/GHOST_PHYSICAL_VALIDATION_MASTER_RUNBOOK.md).

| Preserved hardware XY replay | Dropout-state timeline |
|---|---|
| ![Hardware XY path](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_xy_path.png) | ![IMM status timeline](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_imm_status_timeline.png) |

## Verified hardware evidence

The preserved run `live_camera_calibrated_R_01` contains real USB-webcam AprilTag measurements from the Raspberry Pi and simultaneous formal IMM / GHOST-MH outputs.

| Metric | Recorded value |
|---|---:|
| Run duration | `48.28 s` |
| Vision measurements | `655` |
| Camera pose rate | `13.57 Hz` |
| Formal IMM odometry rate | `30.01 Hz` |
| Heuristic MH odometry rate | `29.99 Hz` |
| Maximum IMM prediction-only steps | `77` |
| Maximum IMM measurement age | `2.849 s` |

The run demonstrates visible tracking, temporary measurement loss, prediction-only propagation, degraded-dropout labeling and reacquisition. These are pipeline and behavior results—not physical accuracy results.

## Implemented architecture

### Hardware estimation and replay

```text
AprilTag target
        |
        v optical image
USB UVC webcam
        |
        v USB + Linux V4L2/UVC
Raspberry Pi / ROS 2 Jazzy
        |
        v
AprilTag pose publisher
/ghost/vision/target_pose
        |
        +-------------------------------+
        |                               |
        v                               v
Formal IMM tracker                GHOST-MH tracker
- motion-model bank               - bounded candidate futures
- mode probabilities              - relative hypothesis weights
- covariance propagation          - operational dropout context
        |                               |
        v                               v
/ghost/tracker_imm/*              /ghost/tracker_mh/*
        \                               /
         +---- recorder / analysis / replay ----+
```

### Deterministic GNC software-in-the-loop

```text
synthetic target truth
        |
noisy / intermittent measurements
        |
formal GHOST IMM
        |
relative-standoff guidance
        |
acceleration-limited controller
        |
actuator lag + follower dynamics
        |
TRACKING / PREDICTION / SAFE_HOLD supervisor
```

The SIL harness uses the repository's formal IMM implementation. It does not arm or command real hardware.

## Implementation and validation status

| Capability | Implemented | Evidence | Current status |
|---|:---:|---|---|
| USB UVC / V4L2 AprilTag pose pipeline | Yes | EMEET C960 live continuity + calibration evidence | Live source/receipt continuity passed; ground-truth dynamic accuracy pending |
| Formal IMM tracker | Yes | Hardware behavior + SIL | Ground-truth hardware performance pending |
| GHOST-MH comparison tracker | Yes | Hardware behavior | Ground-truth hardware performance pending |
| Full symmetric `2 x 2` measurement covariance plumbing | Yes | Accepted direct stationary trial, 885 fixed-window samples | Engineering-review candidate collected; does not validate accuracy or whiteness |
| Prediction-only / degraded / reacquisition telemetry | Yes | Hardware replay | Behavior evidence |
| Closed-loop formal-IMM GNC SIL | Yes | Dedicated CI artifact | Deterministic software-only evidence |
| USB hardware BOM and interface-control record | Yes | Physical machine-readable inventory captured | Public presentation photographs and release review pending |
| Privacy-separated USB hardware inventory capture | Yes | Physical inventory evidence preserved | Public review pending; private identifiers remain excluded |
| Hardened controlled-`R` collection | Yes | `controlled_R_direct_01` + ROS continuity evidence | Stationary covariance gate passed; tracker accuracy still pending grid/campaign |
| Six-point grid analysis and visuals | Yes | Synthetic fixtures/CI | Physical grid pending |
| 55-slot paired IMM/MH campaign protocol | Yes | Predeclared | Physical collection pending |
| Balanced randomized campaign initializer | Yes | Tests/CI | Formal campaign initialization pending |
| Local visual/audio trial conductor | Yes | Tests/CI | Dry-run smoke test pending |
| Immutable plan + audited trial state | Yes | Tests/CI | Hardware outcomes pending |
| Audited campaign analysis and public plots | Yes | Synthetic fixtures/CI | Real accepted trials pending |
| USB timing and Pi resource characterization | Yes | Synthetic `/proc`/JSONL tests | Physical measurements pending |
| SHA-256 evidence packaging and verification | Yes | Tamper-detection tests | Physical evidence packaging pending |
| Parameter/file lock | Yes | Tests/CI | Create after dry runs |
| Machine-readable public claims gate | Yes | Current matrix passes | Pending claims remain disabled |
| Dependency-gated master session checklist | Yes | Tests/CI | Physical session pending |
| Three-take hero demonstration protocol | Yes | Predeclared | Physical takes pending |
| PX4, HIL, vehicle command or flight control | No | None | Not claimed |

## Closed-loop GNC SIL evidence

The dedicated Actions workflow runs three fixed-seed scenarios through the repository's actual formal IMM.

| Scenario | Final standoff error | RMS standoff error after 5 s | Maximum estimator error | Maximum measurement age | Safe-hold time |
|---|---:|---:|---:|---:|---:|
| `nominal_visible` | `0.00114 m` | `0.05319 m` | `0.02673 m` | `0.0 s` | `0.0 s` |
| `short_dropout` | `0.000353 m` | `0.05535 m` | `0.16357 m` | `1.5 s` | `0.0 s` |
| `long_dropout_safe_hold` | `0.00986 m` | `0.31648 m` | `0.41683 m` | `4.0 s` | `2.0 s` |

All scenarios produced finite output. Command acceleration remained bounded by `2.5 m/s²`; the long-dropout case entered safe hold after the `2.0 s` prediction horizon and reacquired after measurements returned.

These are synthetic-truth SIL metrics. They demonstrate estimator-guidance-controller-plant integration, not physical tracking accuracy or flight performance.

## Formal IMM versus GHOST-MH

### Formal IMM

The formal tracker maintains multiple motion-model filters, performs model-conditioned Kalman updates, mixes model states/covariances, updates model probabilities from measurement likelihoods and publishes a combined estimate. During measurement loss it explicitly labels prediction-only and degraded output.

### GHOST-MH

The heuristic tracker publishes bounded candidate futures for operational context during occlusion. Its rankings are **relative hypothesis weights**, not calibrated probabilities. It is retained as a transparent comparison baseline rather than presented as a formal Bayesian estimator.

The paired hardware campaign will report condition-specific endpoint prediction error, first-reacquisition error, reacquisition latency, failures, paired medians, bootstrap confidence intervals and optional Wilcoxon results. No superiority claim is made before protocol-compliant physical trials exist.

## Complete hardware-free validation stack

The repository now contains every major software, methodology and presentation component needed before the next camera session.

### Hardware and reproducibility

- [USB hardware/BOM record](ghost_sim_ros2/docs/GHOST_HARDWARE_BOM.md)
- [Privacy-safe USB inventory capture](ghost_sim_ros2/docs/GHOST_USB_HARDWARE_INVENTORY.md)
- [Public hardware page](https://xpiredruby.github.io/ghost-vins-eskf/hardware.html)
- [Evidence archive and SHA-256 verification](ghost_sim_ros2/docs/GHOST_EVIDENCE_INTEGRITY.md)

### Physical collection and operations

- [Controlled covariance protocol](docs/CONTROLLED_R_COLLECTION_PROTOCOL.md)
- [Hardened controlled-R runbook](ghost_sim_ros2/docs/CONTROLLED_R_COLLECTION_RUNBOOK.md)
- [Direct controlled-R source path](ghost_sim_ros2/docs/DIRECT_CONTROLLED_R_COLLECTION.md)
- [Ground-truth grid protocol](ghost_sim_ros2/docs/GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md)
- [55-trial IMM/MH protocol](ghost_sim_ros2/docs/IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md)
- [Consolidated Phase 2 operator session](ghost_sim_ros2/docs/GHOST_PHASE2_OPERATOR_SESSION.md)
- [Phase 2 candidate tracker parameters](ghost_sim_ros2/config/phase2_candidate_parameters.yaml)
- [Campaign initializer and local conductor](ghost_sim_ros2/docs/GHOST_CAMPAIGN_OPERATIONS.md)
- [Immutable plan / audited outcomes](ghost_sim_ros2/docs/GHOST_CAMPAIGN_STATE.md)
- [Master physical-session runbook](ghost_sim_ros2/docs/GHOST_PHYSICAL_VALIDATION_MASTER_RUNBOOK.md)
- [Machine-readable session checklist](ghost_sim_ros2/docs/PHYSICAL_VALIDATION_SESSION_CHECKLIST.example.json)
- [Three-take hero demo protocol](ghost_sim_ros2/docs/GHOST_HERO_DEMO_PROTOCOL.md)

### Analysis and release discipline

- [Audited campaign analysis](ghost_sim_ros2/docs/GHOST_CAMPAIGN_ANALYSIS.md)
- [Public plot and representative-run rules](ghost_sim_ros2/docs/GHOST_CAMPAIGN_PUBLIC_VISUALS.md)
- [USB timing and Pi runtime validation](ghost_sim_ros2/docs/GHOST_RUNTIME_TIMING_VALIDATION.md)
- [Formal campaign parameter lock](ghost_sim_ros2/docs/GHOST_PARAMETER_LOCK.md)
- [Evidence-bounded public claims review](ghost_sim_ros2/docs/GHOST_RELEASE_CLAIMS_REVIEW.md)
- [Machine-readable claims matrix](ghost_sim_ros2/docs/RELEASE_CLAIMS_MATRIX.example.json)

## Next physical sequence

1. Capture privacy-separated USB hardware inventory and the ten BOM photographs.
2. Rigidly mount the USB webcam and AprilTag; define axes, standoff, grid and motion path.
3. Run the hardened 90-second controlled covariance collection.
4. Keep the same setup and execute the six-point ground-truth grid.
5. Run one dry trial for each of the six campaign conditions.
6. Fix dry-run issues, then create the formal parameter lock.
7. Initialize and freeze the balanced randomized 55-slot campaign.
8. Execute trials using the local conductor; accept/reject through audited state updates.
9. Collect representative Pi runtime and USB timing blocks.
10. Record and preserve three hero demonstration takes.
11. Finalize campaign state, run audited analysis and generate public visuals.
12. Package, verify, copy and reverify the evidence.
13. Promote only validated claims through the machine-readable release gate.

No physical accuracy, covariance or tracker-superiority number will be published before the required evidence exists.

## Key commands

### Build ROS 2 package

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2 --symlink-install
source install/setup.bash
```

### Closed-loop GNC SIL

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/closed_loop_gnc_sil.py \
  --out ghost_gnc_sil/manual
```

### Controlled-R collection

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

### Initialize formal campaign

```bash
python3 ghost_sim_ros2/tools/campaign_operations.py \
  --template ghost_sim_ros2/docs/IMM_MH_CAMPAIGN_MANIFEST.example.json \
  --out ~/ghost_trials/imm_mh_campaign_v1 \
  --resolve-protocol-commit \
  --repo-root .
```

### Run one local cue sequence

```bash
python3 ghost_sim_ros2/tools/trial_conductor.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --sequence 1
```

### Analyze audited campaign

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/campaign_analysis_runner.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --out-dir ~/ghost_trials/imm_mh_campaign_v1/analysis
```

### Package evidence

```bash
python3 ghost_sim_ros2/tools/evidence_integrity.py package \
  --source ~/ghost_trials/imm_mh_campaign_v1 \
  --archive ~/ghost_evidence/imm_mh_campaign_v1.zip \
  --profile campaign \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf
```

## Repository map

```text
ghost-vins-eskf/
├── README.md
├── .github/workflows/        # estimator, GNC, collection, operations, analysis and Pages CI
├── docs/                     # top-level predeclared protocols
├── ghost_sim_ros2/
│   ├── analysis/             # IMM, GNC SIL, covariance, grid, campaign, timing and claims tools
│   ├── docs/                 # reports, runbooks, BOM, replay and public site
│   ├── ghost_sim_ros2/       # ROS 2 nodes
│   ├── launch/               # ROS 2 launch files
│   ├── test/                 # focused unit/integration tests
│   └── tools/                # collection, conductor, locks, inventory and evidence tools
├── src/                      # portable / legacy C++ components
└── tools/                    # Raspberry Pi operator scripts
```

Legacy design documents remain as development history. They are not evidence that every historical ESKF, UKF, PX4, MAVLink, HIL or flight-test concept is implemented in the current hardware package.

## Safe claims

GHOST can currently claim:

- a hardware-integrated USB UVC webcam, Raspberry Pi and ROS 2 AprilTag tracking pipeline;
- a live formal IMM tracker and heuristic MH comparison tracker;
- full covariance plumbing and explicit uncertainty/status telemetry;
- preserved hardware replay evidence through temporary target loss;
- deterministic formal-IMM closed-loop GNC software-in-the-loop evidence;
- bounded acceleration, prediction-horizon supervision, safe hold and reacquisition in SIL;
- predeclared, dependency-gated and integrity-protected physical validation infrastructure;
- reproducible operations, analysis, CI, reports, BOM, public replay and evidence packaging.

GHOST does not currently claim:

- validated real-world tracking accuracy;
- statistically proven IMM superiority;
- production robustness;
- general object tracking beyond AprilTags;
- PX4 or hardware-in-the-loop integration;
- closed-loop autonomous vehicle command;
- flight readiness or flight-test validation.

## License and contact

This repository is a student aerospace/robotics engineering portfolio project. Technical review, reproducibility feedback and GNC/estimation discussion are welcome through GitHub issues.
