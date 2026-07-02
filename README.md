# GHOST — Vision-Only AprilTag Occlusion Tracking Prototype

**Current implemented system:** V1 — Vision-Only Heuristic Hypothesis Bank for AprilTag Occlusion Tracking.

This repository currently contains a working ROS2 Jazzy hardware/software prototype that uses a USB webcam, calibrated AprilTag pose, and a heuristic bank of motion hypotheses to maintain bounded future paths during temporary visual occlusion.

The current live system is **not yet** a formal MHT, formal IMM, active VINS stack, or deployed strapdown IMU + ESKF fusion system. Those are planned roadmap stages and should not be treated as implemented V1 capabilities.

**Author:** Vinayak Manoj Nair — Texas A&M University, B.S. Aerospace Engineering  
**Repository:** `ghost-vins-eskf`  
**Current status:** V1 live vision-only prototype works; validation and estimator upgrades remain open.

---

## Roadmap and Scope

| Version | Status | Scope |
|---|---|---|
| V1 | Current | Vision-only calibrated AprilTag occlusion tracker with a heuristic hypothesis bank |
| V2 | Planned | Formal IMM estimator with likelihood-weighted mode probability updates |
| V3 | Planned | Strapdown IMU + ESKF camera/platform stabilization and VINS-style fusion |

### V1 Current Scope

V1 uses:

- USB webcam or camera stream
- Camera calibration
- AprilTag pose measurement
- ROS2 topic `/ghost/vision/target_pose`
- Heuristic hypothesis bank for occlusion futures
- Browser dashboard and terminal monitor
- Trial recorder and generated reports

V1 does **not** currently claim:

- active strapdown IMU fusion
- active ESKF camera-platform stabilization
- formal IMM mode mixing
- formal MHT data association
- ground-truth validated RMSE
- tagless real-world target tracking

---

## Why the Repository Name Mentions VINS/ESKF

The original architecture targets a GPS-denied vision-inertial tracking system. The repository name reflects that long-term direction. The current deployed software is intentionally smaller: a vision-only V1 prototype built first to prove the live camera → ROS2 → tracker → dashboard → logger pipeline before adding estimator complexity.

This is deliberate sequencing, not a claim that VINS/ESKF is already complete.

---

## Current Live System

```text
USB webcam / camera
        |
        v
calibrated AprilTag pose script
        |
        v
/ghost/vision/target_pose
        |
        v
ghost_sim_ros2.mh_tracker
        |
        +--> /ghost/tracker_mh/target_odom
        +--> /ghost/tracker_mh/futures_json
        +--> /ghost/tracker_mh/status
        |
        v
trial recorder + dashboard + monitor
```

The current tracker maintains ranked heuristic futures such as:

- stationary/hover
- constant velocity
- acceleration
- braking
- lateral motion
- coordinated turn

These are V1 heuristic hypotheses, not a validated formal IMM estimator yet.

---

## Live Hardware Demo

Start the live system on the Raspberry Pi:

```bash
~/ghost_start.sh
```

Check process health:

```bash
~/ghost_status.sh
```

Stop everything:

```bash
~/ghost_stop.sh
```

Open the operator console from a browser on the same network:

```text
http://<pi-ip>:8090
```

The camera-only feed is available at:

```text
http://<pi-ip>:8081
```

When using an SSH tunnel, use:

```text
http://127.0.0.1:8090
http://127.0.0.1:8081
```

---

## Build

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2
source install/setup.bash
```

---

## Current Evidence and Known Limitations

### What works now

- Camera live stream
- Calibrated AprilTag detection
- ROS2 target pose publishing
- Vision-only heuristic occlusion tracker
- Bounded future-path visualization
- Browser dashboard
- Terminal monitor
- Trial recorder
- Automatic trial logs/reports

### Known limitations

- Stationary hidden target behavior needs a dedicated stationary-hold gate.
- Current trial metrics are self-consistency/reacquisition checks, not independent ground truth.
- Existing stationary AprilTag logs show low-frequency colored pose noise, not white pixel noise.
- A measured-grid validation set is still required before real RMSE claims.
- The V1 heuristic bank must be compared against constant-velocity baselines over repeated nonlinear trials.
- V2 IMM and V3 IMU/ESKF work must remain additive until validated.

---

## Validation Status

Current empirical stationary logs show that live AprilTag pose noise is dominated by low-frequency colored drift rather than independent white Gaussian pixel noise. Therefore:

- first-order pinhole covariance is useful as a reference only;
- empirical covariance may include colored noise and setup drift;
- CRLB calculations must be labeled as white-noise diagnostic bounds unless a colored-noise model is added;
- IMM likelihoods should not be trusted on live data until measurement noise is characterized under controlled conditions.

---

## V1 Exit Criteria

V1 is not considered portfolio-ready until the checklist in [`docs/V1_EXIT_CRITERIA.md`](docs/V1_EXIT_CRITERIA.md) is satisfied.

High-level V1 gates:

1. Documentation scope correction
2. Stationary noise characterization
3. Stationary-hold fix implementation
4. Independent ground-truth grid validation
5. Nonlinear trial suite
6. Complexity justification against constant velocity
7. Contribution weighting/reframing in docs

---

## Planned Software Phases

1. Scope/docs correction
2. Noise analysis tooling
3. Stationary-hold gate as a tested standalone module
4. Measurement covariance pipeline
5. Observability and CRLB module
6. Formal IMM estimator in simulation
7. Statistical comparison harness and requirements traceability
8. Hardware/Pi validation runs

---

## Repository Structure

```text
ghost-vins-eskf/
├── README.md
├── docs/
│   ├── V1_EXIT_CRITERIA.md
│   ├── NO_HARDWARE_DEMO.md
│   └── CRITICAL_REVIEW_AND_UPGRADE_ROADMAP.md
├── ghost_sim_ros2/
│   ├── ghost_sim_ros2/
│   │   ├── cv_tracker.py
│   │   ├── mh_tracker.py
│   │   ├── mh_monitor.py
│   │   ├── mh_web_dashboard.py
│   │   └── trial_recorder.py
│   └── analysis/
│       ├── ghost_mh_engine.py
│       ├── ghost_mh_calibrated.py
│       └── ghost_mh_final_no_camera_benchmark.py
├── tools/
│   ├── ghost_start_bg.sh
│   ├── ghost_stop_bg.sh
│   └── ghost_status_bg.sh
├── src/
│   ├── attitude_filter/        # legacy/planned V3 direction unless wired into live V1
│   ├── target_tracker/
│   └── guidance/
└── logs/                       # runtime-generated; not committed
```

---

## Engineering Framing

GHOST V1 does not see through occlusion. It maintains bounded, ranked, physically plausible hypotheses until measurement returns. The goal is not false certainty; the goal is honest probabilistic tracking with logs, baselines, and validation evidence.
