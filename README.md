# GHOST — GPS-Denied Hardware Occlusion-Survivable Tracker

[![GHOST CI](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/ci.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/ci.yml)
[![Closed-Loop GNC SIL](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/closed-loop-gnc-sil.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/closed-loop-gnc-sil.yml)
[![Controlled R Pipeline](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/controlled-r-pipeline.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/controlled-r-pipeline.yml)
![ROS 2 Jazzy](https://img.shields.io/badge/ROS%202-Jazzy-22314E)
![Hardware](https://img.shields.io/badge/hardware-Raspberry%20Pi%20%2B%20AprilTag-2ea44f)
![Validation](https://img.shields.io/badge/accuracy%20validation-in%20progress-f59e0b)

**Hardware-integrated ROS 2 target-state estimation for intermittent vision, plus deterministic formal-IMM software-in-the-loop guidance and control.**

GHOST consumes Raspberry Pi AprilTag pose measurements, runs a formal Interacting Multiple Model (IMM) estimator beside a bounded heuristic multi-hypothesis (MH) tracker, exposes dropout and uncertainty telemetry, and packages the evidence into replayable artifacts. A separate deterministic software-in-the-loop harness connects the same formal IMM to bounded relative-standoff guidance, acceleration-limited control, actuator lag, follower dynamics, and a long-dropout safe-hold supervisor.

**Author:** Vinayak Manoj Nair — Texas A&M University, B.S. Aerospace Engineering, December 2026

> **Evidence boundary:** the preserved hardware run validates the camera-to-ROS-to-tracker pipeline, real-time publication, dropout-state telemetry, and replay. The closed-loop GNC results are deterministic software-in-the-loop evidence using synthetic truth and candidate noise parameters. Controlled measurement covariance, physical ground-truth accuracy, vehicle control, and flight readiness are not yet validated.

## Review GHOST in 60 seconds

1. Open the [public GHOST showcase and hardware replay](https://xpiredruby.github.io/ghost-vins-eskf/).
2. Review the [portfolio packet](ghost_sim_ros2/docs/GHOST_PORTFOLIO_PACKET.md).
3. Inspect the [full project report](ghost_sim_ros2/docs/GHOST_PROJECT_REPORT.md).
4. Review the [closed-loop GNC SIL design](ghost_sim_ros2/docs/GHOST_CLOSED_LOOP_GNC_SIL.md).
5. Audit the [controlled covariance protocol](docs/CONTROLLED_R_COLLECTION_PROTOCOL.md), [hardened collection runbook](ghost_sim_ros2/docs/CONTROLLED_R_COLLECTION_RUNBOOK.md), and [paired hardware campaign](ghost_sim_ros2/docs/IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md).

| Hardware XY replay | Position over time |
|---|---|
| ![Hardware XY path](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_xy_path.png) | ![Hardware position over time](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_position_vs_time.png) |

## Verified hardware evidence

The preserved run `live_camera_calibrated_R_01` contains a real Raspberry Pi AprilTag measurement stream and simultaneous outputs from both trackers.

| Metric | Recorded value |
|---|---:|
| Run duration | `48.28 s` |
| Vision measurements | `655` |
| Camera pose rate | `13.57 Hz` |
| Formal IMM odometry rate | `30.01 Hz` |
| Heuristic MH odometry rate | `29.99 Hz` |
| Maximum IMM prediction-only steps | `77` |
| Maximum IMM measurement age | `2.849 s` |

The run demonstrates visible tracking, temporary measurement loss, prediction-only propagation, degraded-dropout labeling, and reacquisition. These are pipeline and behavior results, not ground-truth accuracy results.

## Implemented system architecture

### Hardware estimation and replay path

```text
Raspberry Pi camera
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

### Deterministic software-in-the-loop GNC path

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

The GNC harness uses the repository's formal IMM implementation. It does not arm or command real hardware.

## Implementation and validation status

| Capability | Implemented | Hardware evidence | Validation status |
|---|:---:|:---:|---|
| AprilTag pose publisher | Yes | Yes | Accuracy pending grid trial |
| Formal IMM tracker | Yes | Yes | Ground-truth performance pending |
| GHOST-MH tracker | Yes | Yes | Ground-truth performance pending |
| Full symmetric `2 x 2` measurement covariance `R` plumbing | Yes | Telemetry verified | Controlled collection pending |
| Split IMM/MH trial recording | Yes | Yes | Evidence integrity feature |
| Dropout status and measurement-age telemetry | Yes | Yes | Behavior evidence |
| Hardened controlled-`R` collection and fixed-window analysis | Yes | Physical smoke test pending | Predeclared collection pending |
| Ground-truth grid analysis | Yes | Collection pending | Pending |
| Paired IMM/MH statistical harness | Yes | Real paired trials pending | Pending |
| Predeclared 55-trial IMM/MH campaign | Yes | Collection pending | Pending |
| Static hardware replay dashboard | Yes | Existing hardware run | Integration demo |
| Public GitHub Pages showcase | Yes | Existing hardware run | Presentation layer |
| Closed-loop formal-IMM GNC SIL | Yes | No | Deterministic software-only evidence |
| PX4, HIL, vehicle command, or flight control | No | No | Not claimed |

## Closed-loop GNC software-in-the-loop evidence

The dedicated Actions workflow runs three fixed-seed scenarios through the repository's actual formal IMM.

| Scenario | Final standoff error | RMS standoff error after 5 s | Maximum estimator error | Maximum measurement age | Safe-hold time |
|---|---:|---:|---:|---:|---:|
| `nominal_visible` | `0.00114 m` | `0.05319 m` | `0.02673 m` | `0.0 s` | `0.0 s` |
| `short_dropout` | `0.000353 m` | `0.05535 m` | `0.16357 m` | `1.5 s` | `0.0 s` |
| `long_dropout_safe_hold` | `0.00986 m` | `0.31648 m` | `0.41683 m` | `4.0 s` | `2.0 s` |

All scenarios produced finite output. Command acceleration remained bounded by `2.5 m/s²`; the long-dropout case entered safe hold after the `2.0 s` prediction horizon and reacquired after measurements returned.

These values are synthetic-truth SIL results. They are useful evidence of estimator-guidance-controller-plant integration, not physical tracking accuracy or flight performance.

## Formal IMM versus GHOST-MH

### Formal IMM

The formal tracker maintains a bank of motion models, performs model-conditioned Kalman updates, mixes model states and covariances, updates model probabilities from measurement likelihoods, and combines the model-conditioned outputs into one estimate. During measurement loss it propagates prediction-only state and explicitly labels stale or degraded output.

### GHOST-MH

The heuristic tracker publishes bounded candidate futures for operational context during occlusion. Its rankings are **relative hypothesis weights**, not calibrated probabilities. It is retained as a transparent comparison baseline and visualization mechanism rather than presented as a formal Bayesian estimator.

The paired bootstrap/Wilcoxon harness in [`analysis/statistical_comparison.py`](ghost_sim_ros2/analysis/statistical_comparison.py) includes known-effect, all-zero, and noisy-null tests. The predeclared 55-trial campaign defines the real-data comparison, but no hardware superiority claim is made before those trials exist.

## Validation infrastructure

### Controlled measurement covariance

The hardened one-terminal workflow:

- records the committed protocol and repository revision;
- requires measured camera-to-tag standoff;
- checks supported V4L2 controls before setting, after setting, after camera open, and after collection;
- requires a live vision sample before starting the 90-second clock;
- resolves the recorder's timestamped child directory automatically;
- enforces the predeclared `15–75 s` fixed window;
- requires at least `10 Hz` fixed-window rate and no sample gap above `0.25 s`;
- produces the required `15–35`, `35–55`, and `55–75 s` diagnostics;
- requires a post-trial physical-integrity attestation;
- preserves rejected runs and their evidence.

### Ground-truth and paired trials

The repository also contains:

- measured-grid bias/RMSE analysis;
- a 55-trial, 6-condition paired IMM/MH campaign;
- unique trial-slot and rejection-reason validation;
- fixed-seed bootstrap confidence intervals;
- Wilcoxon signed-rank reporting when SciPy is available;
- explicit rules against pooling unlike occlusion durations or silently replacing rejected trials.

## Evidence and reproducibility

### Public showcase

The GitHub Pages site packages the existing static hardware JSON, evidence plots, replay dashboard, scope boundary, and reviewer links without requiring ROS installation.

### Key evidence pages

- [Public showcase](https://xpiredruby.github.io/ghost-vins-eskf/)
- [Hardware bag plots](ghost_sim_ros2/docs/GHOST_LIVE_BAG_PLOTS.md)
- [Portfolio packet](ghost_sim_ros2/docs/GHOST_PORTFOLIO_PACKET.md)
- [Full project report](ghost_sim_ros2/docs/GHOST_PROJECT_REPORT.md)
- [Closed-loop GNC SIL](ghost_sim_ros2/docs/GHOST_CLOSED_LOOP_GNC_SIL.md)
- [Career and interview snippets](ghost_sim_ros2/docs/GHOST_CAREER_SNIPPETS.md)
- [Static replay dashboard](ghost_sim_ros2/docs/GHOST_LIVE_REPLAY_DASHBOARD.html)

### Validation and test paths

- [`docs/CONTROLLED_R_COLLECTION_PROTOCOL.md`](docs/CONTROLLED_R_COLLECTION_PROTOCOL.md)
- [`CONTROLLED_R_COLLECTION_RUNBOOK.md`](ghost_sim_ros2/docs/CONTROLLED_R_COLLECTION_RUNBOOK.md)
- [`controlled_r_collection_quality.py`](ghost_sim_ros2/analysis/controlled_r_collection_quality.py)
- [`controlled_r_protocol_analysis.py`](ghost_sim_ros2/analysis/controlled_r_protocol_analysis.py)
- [`GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md`](ghost_sim_ros2/docs/GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md)
- [`IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md`](ghost_sim_ros2/docs/IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md)
- [`validate_campaign_manifest.py`](ghost_sim_ros2/analysis/validate_campaign_manifest.py)
- [`statistical_comparison.py`](ghost_sim_ros2/analysis/statistical_comparison.py)
- [`closed_loop_gnc_sil.py`](ghost_sim_ros2/analysis/closed_loop_gnc_sil.py)

## Next physical campaign

1. Execute the hardened predeclared controlled covariance trial.
2. Reject or accept it using the saved readbacks, timing gates, and operator attestation.
3. Keep the same camera setup for the measured 5–6 point ground-truth grid.
4. Publish covariance, stability, bias, RMSE, mean error, maximum error, repeatability, sample count, and sample rate.
5. Pin the paired-campaign protocol commit before collection.
6. Execute the 55 planned visible/occluded trials.
7. Report condition-specific paired effects, confidence intervals, reacquisition latency, and failure rates.
8. Add Raspberry Pi CPU, memory, and thermal evidence.

No physical accuracy or superiority number will be published before the required data exist.

## Build and run

### ROS 2 package

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2 --symlink-install
source install/setup.bash
```

### Software-only tracker demo

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

### Closed-loop GNC SIL

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/closed_loop_gnc_sil.py \
  --out ghost_gnc_sil/manual
```

### Hardened controlled-`R` collection

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

### Raspberry Pi operator scripts

```bash
~/ghost_start.sh
~/ghost_status.sh
~/ghost_stop.sh
```

## Repository map

```text
ghost-vins-eskf/
├── README.md
├── .github/workflows/        # CI, controlled-R, GNC SIL and Pages
├── docs/                     # predeclared top-level protocols
├── ghost_sim_ros2/
│   ├── analysis/             # IMM, GNC SIL, covariance, grid and statistics
│   ├── docs/                 # reports, protocols, replay and public site
│   ├── ghost_sim_ros2/       # ROS 2 nodes
│   ├── launch/               # ROS 2 launch files
│   ├── test/                 # unit and integration-focused tests
│   └── tools/                # collection, replay, plotting and export tools
├── src/                      # portable / legacy C++ components
└── tools/                    # Raspberry Pi operator scripts
```

Legacy design documents remain as development history. They are not evidence that every historical ESKF, UKF, PX4, MAVLink, HIL, or flight-test concept is implemented in the current hardware package.

## Safe claims

GHOST can currently claim:

- a hardware-integrated Raspberry Pi and ROS 2 AprilTag tracking pipeline;
- a live formal IMM tracker and heuristic MH comparison tracker;
- full covariance plumbing and explicit uncertainty/status telemetry;
- preserved hardware replay evidence through temporary target loss;
- deterministic formal-IMM closed-loop GNC software-in-the-loop evidence;
- bounded acceleration, prediction-horizon supervision, safe hold, and reacquisition in SIL;
- hardened predeclared physical collection and paired-campaign infrastructure;
- reproducible analysis, CI, reports, artifacts, and a public replay site.

GHOST does not currently claim:

- validated real-world tracking accuracy;
- statistically proven IMM superiority;
- production robustness;
- general object tracking beyond AprilTags;
- PX4 or hardware-in-the-loop integration;
- closed-loop autonomous vehicle command;
- flight readiness or flight-test validation.

## License and contact

This repository is a student aerospace/robotics engineering portfolio project. Technical review, reproducibility feedback, and GNC/estimation discussion are welcome through GitHub issues.
