# GHOST — GPS-Denied Hardware Occlusion-Survivable Tracker

[![GHOST CI](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/ci.yml/badge.svg)](https://github.com/XpiredRuby/ghost-vins-eskf/actions/workflows/ci.yml)
![ROS 2 Jazzy](https://img.shields.io/badge/ROS%202-Jazzy-22314E)
![Hardware](https://img.shields.io/badge/hardware-Raspberry%20Pi%20%2B%20AprilTag-2ea44f)
![Validation](https://img.shields.io/badge/accuracy%20validation-in%20progress-f59e0b)

**Hardware-integrated ROS 2 target-state estimation for intermittent vision and temporary target occlusion.**

GHOST consumes Raspberry Pi AprilTag pose measurements, runs a formal Interacting Multiple Model (IMM) estimator beside a bounded heuristic multi-hypothesis (MH) tracker, and exposes the estimator state, mode probabilities, relative hypothesis weights, measurement age, and prediction-only behavior through ROS 2 telemetry and replay artifacts.

**Author:** Vinayak Manoj Nair — Texas A&M University, B.S. Aerospace Engineering, December 2026

> **Evidence boundary:** the preserved hardware run validates the live ROS 2 measurement and tracker pipeline, real-time publication rates, dropout-state telemetry, and replay tooling. Controlled measurement covariance and ground-truth accuracy trials are prepared but not yet collected. GHOST does not currently claim flight readiness, production accuracy, or closed-loop vehicle control.

## Review GHOST in 60 seconds

1. See the final hardware trajectory and tracker overlays below.
2. Review the [portfolio packet](ghost_sim_ros2/docs/GHOST_PORTFOLIO_PACKET.md).
3. Inspect the [full project report](ghost_sim_ros2/docs/GHOST_PROJECT_REPORT.md).
4. Open the [static replay dashboard](ghost_sim_ros2/docs/GHOST_LIVE_REPLAY_DASHBOARD.html) through a local HTTP server.
5. Audit the [controlled covariance protocol](docs/CONTROLLED_R_COLLECTION_PROTOCOL.md) and [ground-truth grid protocol](ghost_sim_ros2/docs/GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md).

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

## Current implemented pipeline

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
         \                             /
          +---- recorder / analysis / replay ----+
```

Primary live outputs:

```text
/ghost/tracker_imm/target_odom
/ghost/tracker_imm/futures_json
/ghost/tracker_imm/status

/ghost/tracker_mh/target_odom
/ghost/tracker_mh/futures_json
/ghost/tracker_mh/status
```

## Implementation and validation status

| Capability | Implemented | Hardware evidence | Accuracy validated |
|---|:---:|:---:|:---:|
| AprilTag pose publisher | Yes | Yes | Pending grid trial |
| Formal IMM tracker | Yes | Yes | Pending ground truth |
| GHOST-MH tracker | Yes | Yes | Pending ground truth |
| Full symmetric `2 x 2` measurement covariance `R` plumbing | Yes | Telemetry verified | Controlled collection pending |
| Split IMM/MH trial recording | Yes | Yes | Not an accuracy claim |
| Dropout status and measurement-age telemetry | Yes | Yes | Behavior evidence only |
| Ground-truth grid analysis | Yes | Collection pending | Pending |
| Paired IMM/MH statistical harness | Yes | Real paired trials pending | Pending |
| Static replay dashboard | Yes | Existing hardware run | Integration demo only |
| Public one-click hosted demo | Export plan exists | Pending deployment | Not applicable |
| Closed-loop guidance and control | Planned | No | No |

### GNC scope

GHOST currently demonstrates the **navigation/estimation core** of a GNC stack: measurement modeling, state estimation, uncertainty propagation, motion-model interaction, dropout handling, and estimator telemetry.

Guidance and control interfaces exist only as downstream-facing integration work. The current evidence does **not** show a validated guidance law, flight controller, autonomous vehicle command, or flight test. A closed-loop simulation and safety-supervised guidance/control layer are future milestones.

## Formal IMM versus GHOST-MH

### Formal IMM

The formal tracker maintains a bank of motion models, performs model-conditioned Kalman updates, mixes model states and covariances, and publishes valid IMM mode probabilities. During measurement loss it propagates prediction-only state and explicitly labels stale or degraded output.

### GHOST-MH

The heuristic tracker publishes bounded candidate futures for operational context during occlusion. Its ranking values are **relative hypothesis weights**, not calibrated probabilities. It is retained as a transparent comparison baseline and visualization mechanism rather than presented as a formal Bayesian estimator.

A paired bootstrap/Wilcoxon comparison harness is implemented in [`analysis/statistical_comparison.py`](ghost_sim_ros2/analysis/statistical_comparison.py). It has not yet been applied to the repeated ground-truth hardware trials required for a superiority claim.

## Evidence and reproducibility

### Static replay dashboard

The dashboard replays the preserved hardware dataset with:

- raw AprilTag measurements;
- IMM and MH state estimates;
- IMM mode probabilities;
- tracker status transitions;
- measurement age and prediction-only steps;
- future prediction tails;
- XY and position-versus-time views.

Run it locally:

```bash
cd ghost_sim_ros2/docs
python3 -m http.server 8000 --bind 0.0.0.0
```

Then open:

```text
http://localhost:8000/GHOST_LIVE_REPLAY_DASHBOARD.html
```

GitHub displays HTML source rather than reliably running the local JSON-backed application. A public hosted replay remains a planned presentation milestone.

### Hardware evidence pages

- [Hardware bag plots](ghost_sim_ros2/docs/GHOST_LIVE_BAG_PLOTS.md)
- [Portfolio packet](ghost_sim_ros2/docs/GHOST_PORTFOLIO_PACKET.md)
- [Full project report](ghost_sim_ros2/docs/GHOST_PROJECT_REPORT.md)
- [Career and interview snippets](ghost_sim_ros2/docs/GHOST_CAREER_SNIPPETS.md)
- [Static replay dashboard](ghost_sim_ros2/docs/GHOST_LIVE_REPLAY_DASHBOARD.html)

### Validation infrastructure already merged

- Controlled stationary covariance protocol: [`docs/CONTROLLED_R_COLLECTION_PROTOCOL.md`](docs/CONTROLLED_R_COLLECTION_PROTOCOL.md)
- Controlled collection helper: [`collect_controlled_r_trial.sh`](ghost_sim_ros2/tools/collect_controlled_r_trial.sh)
- Controlled collection runbook: [`CONTROLLED_R_COLLECTION_RUNBOOK.md`](ghost_sim_ros2/docs/CONTROLLED_R_COLLECTION_RUNBOOK.md)
- Ground-truth grid protocol: [`GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md`](ghost_sim_ros2/docs/GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md)
- Grid analysis: [`grid_validation_analysis.py`](ghost_sim_ros2/analysis/grid_validation_analysis.py)
- Paired statistical comparison: [`statistical_comparison.py`](ghost_sim_ros2/analysis/statistical_comparison.py)
- Static demo export: [`export_demo_artifact.py`](ghost_sim_ros2/tools/export_demo_artifact.py)
- Hosted-demo plan: [`REPLIT_DEMO_PLAN.md`](ghost_sim_ros2/docs/REPLIT_DEMO_PLAN.md)

## Next validation campaign

The next physical session is predeclared and deliberately sequenced:

1. Rigidly mount the camera and AprilTag.
2. Lock and record supported camera controls.
3. Record exactly `90 s` for stationary covariance estimation.
4. Analyze only the fixed `15–75 s` window.
5. Check covariance stability across three fixed sub-windows.
6. Keep the same camera setup for a measured 5–6 point ground-truth grid.
7. Report bias, RMSE, mean error, maximum error, repeatability, sample count, and sample rate.
8. Run repeated visible/occluded trajectories for paired IMM/MH comparison.

No validated accuracy number will be published before those data exist.

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

### Full integrated demo

```bash
ros2 launch ghost_sim_ros2 ghost_full_demo.launch.py
```

### Raspberry Pi operator scripts

```bash
~/ghost_start.sh
~/ghost_status.sh
~/ghost_stop.sh
```

The live operator console is served on port `8090`, and the camera-only view is served on port `8081` when the hardware stack is active.

## Repository map

```text
ghost-vins-eskf/
├── README.md
├── .github/workflows/ci.yml
├── docs/
│   ├── CONTROLLED_R_COLLECTION_PROTOCOL.md
│   └── CRITICAL_REVIEW_AND_UPGRADE_ROADMAP.md
├── ghost_sim_ros2/
│   ├── analysis/          # IMM/MH analysis, covariance, grid and statistics
│   ├── docs/              # reports, runbooks, replay dashboard and evidence
│   ├── ghost_sim_ros2/    # ROS 2 nodes
│   ├── launch/            # ROS 2 launch files
│   ├── test/              # unit and integration-focused tests
│   └── tools/             # collection, replay, plotting and export tools
├── src/                   # portable / legacy C++ estimator components
└── tools/                 # Raspberry Pi operator scripts
```

Legacy design documents remain in the repository as development history. They should not be interpreted as evidence that every historical ESKF, UKF, guidance, PX4, or flight-test concept is implemented in the current hardware package.

## Safe claims

GHOST can currently claim:

- a hardware-integrated Raspberry Pi and ROS 2 AprilTag tracking pipeline;
- a live formal IMM tracker and heuristic MH comparison tracker;
- full covariance plumbing and explicit uncertainty/status telemetry;
- preserved hardware replay evidence through temporary target loss;
- reproducible analysis, reporting, testing, and replay infrastructure;
- predeclared controlled covariance and ground-truth validation protocols.

GHOST does not currently claim:

- validated real-world tracking accuracy;
- statistically proven IMM superiority;
- production robustness;
- general object tracking beyond AprilTags;
- closed-loop autonomous guidance or control;
- flight readiness or flight-test validation.

## License and contact

This repository is a student aerospace/robotics engineering portfolio project. Technical review, reproducibility feedback, and GNC/estimation discussion are welcome through GitHub issues.
