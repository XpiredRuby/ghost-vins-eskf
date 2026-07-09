# GHOST — GPS-Denied Hardware Occlusion-Survivable Tracker

## Portfolio Snapshot

ROS 2 target-tracking autonomy prototype for intermittent AprilTag visibility, integrated with Raspberry Pi AprilTag hardware replay evidence and live formal IMM plus heuristic MH tracking.

- **Author:** Vinayak Manoj Nair — Texas A&M University, B.S. Aerospace Engineering (Dec 2026)
- **Repo:** `ghost-vins-eskf`
- **Current status:** Hardware-integrated final replay package complete for pipeline, telemetry, and dashboard evidence.
- **Evidence caveat:** Current hardware evidence validates live ROS 2 pipeline operation, topic rates, dropout/status telemetry, and replay tooling. It does not yet constitute report-grade real-world estimator accuracy validation because controlled hardware measurement covariance R is pending verified stationary noise characterization.

Key hardware replay metrics from the final calibrated hardware run:

| Metric | Value |
| --- | ---: |
| Final bag | `live_camera_calibrated_R_01` |
| Duration | `48.28 s` |
| Vision measurements | `655` |
| Camera pose rate | `13.57 Hz` |
| IMM odom rate | `30.01 Hz` |
| MH odom rate | `29.99 Hz` |
| Max IMM prediction-only steps | `77` |
| Max IMM measurement age | `2.849 s` |

Direct review links:

- Career snippets: [`ghost_sim_ros2/docs/GHOST_CAREER_SNIPPETS.md`](ghost_sim_ros2/docs/GHOST_CAREER_SNIPPETS.md)
- Portfolio packet: [`ghost_sim_ros2/docs/GHOST_PORTFOLIO_PACKET.md`](ghost_sim_ros2/docs/GHOST_PORTFOLIO_PACKET.md)
- Final project report: [`ghost_sim_ros2/docs/GHOST_PROJECT_REPORT.md`](ghost_sim_ros2/docs/GHOST_PROJECT_REPORT.md)
- Final hardware bag plots: [`ghost_sim_ros2/docs/GHOST_LIVE_BAG_PLOTS.md`](ghost_sim_ros2/docs/GHOST_LIVE_BAG_PLOTS.md)
- Live replay dashboard: [`ghost_sim_ros2/docs/GHOST_LIVE_REPLAY_DASHBOARD.html`](ghost_sim_ros2/docs/GHOST_LIVE_REPLAY_DASHBOARD.html)

View the static replay dashboard locally:

```bash
cd ghost_sim_ros2/docs
python3 -m http.server 8000 --bind 0.0.0.0
```

Then open `http://localhost:8000/GHOST_LIVE_REPLAY_DASHBOARD.html`. GitHub may display the HTML source instead of executing the local JSON-backed dashboard, so local serving is the intended review path.

## Current Evidence

### Final Hardware Replay Package

The completed evidence package replays the final calibrated Raspberry Pi AprilTag bag with raw vision measurements, formal IMM tracking, heuristic MH tracking, status transitions, prediction tails, plots, and a static dashboard. The live Raspberry Pi operator console remains useful for demos, while the replay package is the primary reviewer-facing artifact.

![Final hardware XY path](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_xy_path.png)

![Final hardware position over time](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_position_vs_time.png)

![Formal IMM status timeline](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_imm_status_timeline.png)

![Final hardware topic rates](ghost_sim_ros2/docs/assets/ghost_live_plots/ghost_live_topic_rates.png)

### Live GHOST-MH Hardware Demo

The live system runs on the Raspberry Pi with a USB webcam and 10 cm AprilTag target. It publishes calibrated target pose into ROS2, runs the GHOST-MH relative-hypothesis-weight tracker, and serves a combined browser operator console.

- Operator console: `http://<pi-ip>:8090`
- Camera-only view: `http://<pi-ip>:8081`

### Earlier Synthetic / Parameter-Sweep Evidence

These older artifacts remain useful for understanding the software-only development path, but the final hardware replay above is the primary review evidence.

![GHOST synthetic tracking evidence](analysis/ghost_tracking_evidence.png)

![Tracker parameter sweep summary](analysis/tracker_sweep_summary.png)

## What Works Now

- USB webcam bring-up and browser live stream
- AprilTag detection and calibrated pose viewer
- Camera calibration workflow
- Real camera pose publisher into `/ghost/vision/target_pose`
- GHOST-MH bounded multi-hypothesis tracker
- Ranked probabilistic future paths during occlusion
- Safe reset after max occlusion horizon instead of infinite hallucination
- Combined browser operator console on port `8090`
- Terminal monitor and background service-style launcher
- ROS2 Jazzy synthetic target measurement publisher
- 2D constant-velocity Kalman tracker baseline
- Occlusion/dropout coasting simulation
- CSV evidence logging
- Offline tracker parameter sweep
- MPU-6050 I2C watchdog ROS2 node with real bump-detection evidence
- Gazebo/PX4-facing bridge topics:
  - `/ghost/gazebo/target_pose`
  - `/ghost/gazebo/target_twist`
  - `/ghost/px4/target_setpoint`

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

The camera-only feed remains available at:

```text
http://<pi-ip>:8081
```

## No-Hardware Demo

The software-only pipeline runs without camera, AprilTag print, IMU, Gazebo, or PX4 hardware:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2
source install/setup.bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

Expected ROS2 topics:

```text
/ghost/vision/target_pose
/ghost/tracker/target_odom
/ghost/gazebo/target_pose
/ghost/gazebo/target_twist
/ghost/px4/target_setpoint
/ghost/sim/target_truth
```

Full runbook: [`docs/NO_HARDWARE_DEMO.md`](docs/NO_HARDWARE_DEMO.md)

Integrated hardware/software demo: [ghost_sim_ros2/docs/FULL_INTEGRATED_DEMO.md](ghost_sim_ros2/docs/FULL_INTEGRATED_DEMO.md)

```bash
ros2 launch ghost_sim_ros2 ghost_full_demo.launch.py
```

## Completed Review Package

The previous replay and report packaging milestone is complete for the final calibrated AprilTag hardware bag. Reviewers can inspect:

1. Static replay dashboard with local JSON-backed playback.
2. Formal IMM and heuristic MH side-by-side qualitative replay, with statistical comparison pending a dedicated harness.
3. Hardware bag plots for XY path, position over time, status timelines, and topic rates.
4. A final project report and concise portfolio packet.
5. Career-facing snippets for resume, LinkedIn, GitHub, and interview use.

The critical review roadmap remains available for historical context and future extensions: [`docs/CRITICAL_REVIEW_AND_UPGRADE_ROADMAP.md`](docs/CRITICAL_REVIEW_AND_UPGRADE_ROADMAP.md).

## Hardware Scope And Future Work

Current hardware replay evidence covers a calibrated Raspberry Pi AprilTag run with both trackers running side by side. The package does not claim flight test, production deployment, closed-loop vehicle command, real drone autonomy, or onboard vehicle command.

Useful future work includes verified stationary noise characterization for measurement covariance R, a statistical IMM/MH comparison harness, larger trial sets, measured ground-truth trajectories, more lighting and motion-blur tests, longer occlusions, and non-AprilTag perception after the AprilTag pipeline path.

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                     CAMERA PLATFORM (static tripod)                 │
│                                                                     │
│  [ICM-42688-P]──SPI 1000Hz + DRDY ISR──┐                           │
│  [MPU-6050]────I2C  400Hz + DRDY ISR──┤                           │
│  [IMX296 CSI]──728×544 decimated───────┤                           │
│  [IMX296 Strobe]──GPIO22 HW timestamp──┘                           │
│                            │                                        │
│                    ┌───────▼────────┐                               │
│                    │  Raspberry Pi  │                               │
│                    │     4B 4GB     │                               │
│                    └───────┬────────┘                               │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
  │  FILTER 1   │   │  FILTER 2    │   │   GUIDANCE   │
  │  9-state    │   │  CV / CTRV   │   │   ProNav TPN │
  │  ESKF       │──▶│  UKF         │──▶│  a_cmd (NED) │
  │  1000 Hz    │   │  vision Hz   │   │              │
  │             │   │ [px,py,v,    │   └──────┬───────┘
  │ q_cam       │   │  psi,ψ̇]     │          │
  │ b_a  b_g    │   │              │          │ UDP MAVLink
  └─────────────┘   └──────────────┘          │ port 14540
         ▲                  ▲                  ▼
         │                  │        ┌──────────────────┐
     IMU only          AprilTag      │  PX4 SITL +      │
    (no camera)       + opt-flow     │  Gazebo Fortress  │
                                     │  (laptop)        │
                                     └──────────────────┘
```

- **Target:** RC car or hand-moved target with 10 cm × 10 cm AprilTag 36h11 on a flat floor.
- **Occlusion:** Target moves behind an object. GHOST-MH predicts bounded relative-weight future hypotheses and resets after the configured validity horizon.

---

## Hardware

| Component        | Part                                  | Role                              |
|------------------|---------------------------------------|-----------------------------------|
| Compute          | Raspberry Pi 4B 4GB                   | Runs both filters at full rate    |
| Camera           | USB webcam / IMX296 Global Shutter    | AprilTag detection + pose source  |
| Primary IMU      | ICM-42688-P SPI breakout              | Future 1000 Hz attitude ESKF input |
| Watchdog IMU     | MPU-6050 I2C breakout                 | 100 ms disagreement fault flag    |
| RC Car / target  | 1:20 scale or hand-moved tag board    | Tracked target                    |
| AprilTag         | 36h11 tag0, 10 cm × 10 cm laminated   | Vision measurement source         |
| Occlusion object | Shoebox / board / wall segment        | Occlusion test scenario           |

**Budget target: ~$190 total.** No GPS. Optional future guidance closes over UDP MAVLink to PX4 SITL.

---

## The Two Filters

### Filter 1 — 9-State Attitude ESKF (`src/attitude_filter/`)

Runs at **1000 Hz**, driven by the ICM-42688-P IMU over SPI.

Estimates the camera platform's orientation as a quaternion (`q_cam`) plus accelerometer bias (`b_a`) and gyro bias (`b_g`). The output rotation matrix `R_cam_to_NED` is used by Filter 2 to convert AprilTag detections from camera frame into NED world coordinates.

**Three update mechanisms:**

- **Gravity update** — uses the accelerometer reading as a gravity direction measurement when the platform is not accelerating. Produces NIS logged to `logs/nis_camera_gravity.csv`.
- **ZARU (Zero Angular Rate Update)** — fires at 1 Hz on a static platform; treats the absence of angular rate as a pseudo-measurement to correct gyro bias.
- **Sage-Husa adaptive noise** — recursively updates the measurement noise estimate R̂ with a forgetting factor of 0.98; enforces positive definiteness via eigenvalue floor.

### Filter 2 — Target Tracker

The original design contains CV/CTRV filters. The current live ROS2 demo additionally includes `ghost_sim_ros2.mh_tracker`, a bounded multi-hypothesis relative-weight tracker that subscribes to `/ghost/vision/target_pose` and publishes:

```text
/ghost/tracker_mh/target_odom
/ghost/tracker_mh/futures_json
/ghost/tracker_mh/status
```

During occlusion, the live tracker maintains ranked future hypotheses such as constant velocity, braking/hovering, lateral motion, turning, and acceleration. It does not claim hidden-state certainty.

---

## Repository Structure

```text
ghost-vins-eskf/
├── README.md
├── GHOST_V10.md                          # Legacy design document
├── GHOST_V12_USB_WEBCAM.md               # USB webcam design document
├── docs/
│   ├── NO_HARDWARE_DEMO.md
│   └── CRITICAL_REVIEW_AND_UPGRADE_ROADMAP.md
├── ghost_sim_ros2/
│   ├── docs/
│   │   ├── GHOST_CAREER_SNIPPETS.md
│   │   ├── GHOST_PORTFOLIO_PACKET.md
│   │   ├── GHOST_PROJECT_REPORT.md
│   │   ├── GHOST_LIVE_BAG_PLOTS.md
│   │   └── GHOST_LIVE_REPLAY_DASHBOARD.html
│   ├── ghost_sim_ros2/
│   │   ├── cv_tracker.py
│   │   ├── mh_tracker.py
│   │   ├── mh_monitor.py
│   │   └── mh_web_dashboard.py
│   └── analysis/
│       ├── ghost_mh_engine.py
│       ├── ghost_mh_calibrated.py
│       └── ghost_mh_final_no_camera_benchmark.py
├── tools/
│   ├── ghost_start_bg.sh
│   ├── ghost_stop_bg.sh
│   └── ghost_status_bg.sh
├── src/
│   ├── attitude_filter/
│   ├── target_tracker/
│   └── guidance/
├── analysis/
├── test/
└── logs/                                 # Runtime-generated — not committed
```

---

## Build

> Requires: ROS2 Jazzy for the live Python demo. Legacy C++ components require CMake ≥ 3.16, Eigen3, and Google Test.

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2
source install/setup.bash
```
