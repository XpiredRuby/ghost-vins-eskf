# GHOST — GPS-Denied Hardware Occlusion-Survivable Tracker

> **Current baseline:** GHOST V12 — USB webcam + ROS2 synthetic tracking pipeline.  
> **Current working demo:** no-hardware ROS2 tracking simulation with CSV logging, tracker sweep evidence, and Gazebo/PX4-facing bridge topics.  
> **Camera demo:** `tools/ghost_live_apriltag_pose_calibrated.py` runs the USB webcam + calibrated AprilTag live browser overlay at `http://<pi-ip>:8081`.  
> **Spec:** [`GHOST_V12_USB_WEBCAM.md`](./GHOST_V12_USB_WEBCAM.md). `GHOST_V10.md` is retained as legacy reference.

**Author:** Vinayak Manoj Nair — Texas A&M University, B.S. Aerospace Engineering (Dec 2026)  
**Repo:** `ghost-vins-eskf`  
**Status:** V12 no-hardware ROS2 demo complete; MPU-6050 ROS2 watchdog validated on Raspberry Pi; camera validation remains.

## Current Evidence

### ROS2 Synthetic Tracking

![GHOST tracking evidence](analysis/ghost_tracking_evidence.png)

### Tracker Sweep

![Tracker sweep summary](analysis/tracker_sweep_summary.png)

## What Works Now

- USB webcam bring-up and browser live stream
- AprilTag detection and calibrated pose viewer
- Camera calibration workflow
- ROS2 Jazzy synthetic target measurement publisher
- 2D constant-velocity Kalman tracker
- Occlusion/dropout coasting simulation
- CSV evidence logging
- Offline tracker parameter sweep
- MPU-6050 I2C watchdog ROS2 node with real bump-detection evidence
- Gazebo/PX4-facing bridge topics:
  - `/ghost/gazebo/target_pose`
  - `/ghost/gazebo/target_twist`
  - `/ghost/px4/target_setpoint`

## No-Hardware Demo

The current software-only pipeline runs without camera, AprilTag print, IMU, Gazebo, or PX4 hardware:

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

## Hardware Next

The remaining project work is hardware validation:

1. Print the 10 cm `tag36h11` AprilTag and validate real range/pose.
2. Publish real webcam AprilTag measurements into ROS2.
3. Add final real-world validation plots and demo video.

## Architecture

```
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
  │             │   │              │   └──────┬───────┘
  │ q_cam       │   │ [px,py,v,    │          │
  │ b_a  b_g    │   │  psi,ψ̇]     │          │ UDP MAVLink
  └─────────────┘   └──────────────┘          │ port 14540
         ▲                  ▲                  ▼
         │                  │        ┌──────────────────┐
     IMU only          AprilTag      │  PX4 SITL +      │
    (no camera)       + opt-flow     │  Gazebo Fortress  │
                                     │  (laptop)        │
                                     └──────────────────┘
```

**Target:** RC car with 10 cm × 10 cm AprilTag 36h11 on a flat floor.  
**Occlusion:** Car drives behind a shoebox → Filter 2 coasts on velocity prediction. IMU plays no role in car motion; it only detects camera platform disturbances.

---

## Hardware

| Component        | Part                                  | Role                              |
|------------------|---------------------------------------|-----------------------------------|
| Compute          | Raspberry Pi 4B 4GB                   | Runs both filters at full rate    |
| Camera           | innomaker IMX296 Global Shutter (CSI) | AprilTag detection + optical flow |
| Primary IMU      | ICM-42688-P SPI breakout              | 1000 Hz attitude ESKF input       |
| Watchdog IMU     | MPU-6050 I2C breakout                 | 100 ms disagreement fault flag    |
| RC Car           | 1:20 scale, flat roof                 | Tracked target                    |
| AprilTag         | 36h11 tag0, 10 cm × 10 cm laminated   | Vision measurement source         |
| Occlusion object | Shoebox                               | Occlusion test scenario           |

**Budget: ~$190 total.** No Pixhawk, no GPS — guidance closes over UDP MAVLink to PX4 SITL.

---

## The Two Filters

### Filter 1 — 9-State Attitude ESKF (`src/attitude_filter/`)

Runs at **1000 Hz**, driven by the ICM-42688-P IMU over SPI.

Estimates the camera platform's orientation as a quaternion (`q_cam`) plus accelerometer bias (`b_a`) and gyro bias (`b_g`). The output rotation matrix `R_cam_to_NED` is used by Filter 2 to convert AprilTag detections from camera frame into NED world coordinates.

**Three update mechanisms:**
- **Gravity update** — uses the accelerometer reading as a gravity direction measurement when the platform is not accelerating. Produces NIS logged to `logs/nis_camera_gravity.csv` (CI-gated at χ²(3), 95%).
- **ZARU (Zero Angular Rate Update)** — fires at 1 Hz on a static platform; treats the absence of angular rate as a pseudo-measurement to correct gyro bias. NIS logged to `logs/nis_camera_zaru.csv` (*not* CI-gated — ZARU is static-platform only).
- **Sage-Husa adaptive noise** — recursively updates the measurement noise estimate R̂ with a forgetting factor of 0.98; enforces positive definiteness via eigenvalue floor.

### Filter 2 — CV/CTRV Kinematic Filter (`src/target_tracker/`)

Runs at the **vision frame rate** (~25–45 fps).

Tracks the RC car's 2-D floor position and velocity. Two parallel models:

- **CV (Constant Velocity)** — 6-state `[px, py, pz, vx, vy, vz]`. EKF with linear state transition and Singer model process noise. Observes position from the AprilTag pose.
- **CTRV (Constant Turn Rate and Velocity)** — 5-state `[px, py, v, ψ, ψ̇]`. UKF with nonlinear sigma-point propagation. Singularity guard fires at `|ψ̇| < 1e-4 rad/s`, reverting to CV straight-line equations.

**IMU data never enters this filter.** The IMU is mounted on the static tripod, not the moving car. During occlusion the filter simply propagates its kinematic model forward. NIS logged to `logs/nis_target_tracker.csv` (CI-gated at χ²(3), 95%).

---

## Repository Structure

```
ghost-vins-eskf/
├── README.md
├── GHOST_V10.md                          # Full design document
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml                        # NIS-gated CI pipeline
├── src/
│   ├── attitude_filter/                  # Filter 1 — 9-state ESKF
│   │   ├── eskf.hpp / eskf.cpp
│   │   ├── sage_husa.hpp / sage_husa.cpp
│   │   └── zaru.hpp / zaru.cpp
│   ├── target_tracker/                   # Filter 2 — CV/CTRV
│   │   ├── cv_filter.hpp / cv_filter.cpp
│   │   └── ctrv_filter.hpp / ctrv_filter.cpp
│   └── guidance/                         # TPN ProNav
│       ├── pronav.hpp / pronav.cpp
├── analysis/
│   └── nis_validation.py                 # NIS χ² gate (CLI tool)
├── test/
│   ├── test_eskf.cpp
│   └── test_pronav.cpp
└── logs/                                 # Runtime-generated — not committed
    ├── nis_camera_gravity.csv
    ├── nis_camera_zaru.csv
    └── nis_target_tracker.csv
```

---

## Build

> Requires: CMake ≥ 3.16, Eigen3, Google Test (Ubuntu 22.04 recommended)

```bash
sudo apt-get update
sudo apt-get install -y cmake libeigen3-dev libgtest-dev

mkdir build && cd build
cmake ..
make -j$(nproc)
ctest --output-on-failure
```

---

## Run the NIS CI Gate Locally

After a recording session, NIS logs are written to `logs/`. Validate them against the χ²(3) distribution at 95% confidence:

```bash
# Attitude filter — gravity update NIS
python3 analysis/nis_validation.py \
  --log logs/nis_camera_gravity.csv \
  --dof 3 \
  --confidence 0.95 \
  --fail-on-violation

# Target tracking filter NIS
python3 analysis/nis_validation.py \
  --log logs/nis_target_tracker.csv \
  --dof 3 \
  --confidence 0.95 \
  --fail-on-violation

# ZARU NIS — informational only, no pass/fail gate
python3 analysis/nis_validation.py \
  --log logs/nis_camera_zaru.csv \
  --dof 3 \
  --confidence 0.95
```

Exit code 0 = filter is statistically consistent. Exit code 1 = filter is overconfident or diverging — tune Q/R.

---

## CI Pipeline

GitHub Actions runs on every push and pull request to `main`:

1. **`build`** — installs Eigen3 + GTest, compiles all targets, runs `ctest`.
2. **`nis_gate_attitude`** — validates `logs/nis_camera_gravity.csv` (needs `build`).
3. **`nis_gate_target`** — validates `logs/nis_target_tracker.csv` (needs `build`).

`nis_camera_zaru.csv` is deliberately excluded from CI gating — ZARU is a static-platform-only pseudo-measurement, not valid during dynamic rosbag replay.

---

## Engineering Decisions and Documented Fixes

Twenty implementation flaws were identified and corrected during development:

| # | Component | Flaw | Fix |
|---|-----------|------|-----|
| 1 | ProNav | `v_drone_NED` dead parameter in `compute()` | Removed from signature |
| 2 | ProNav test | Collinear geometry → `Omega = 0` → test always passed trivially | Added lateral offset `(10, 2, 0)` |
| 3 | CV filter | Naive `P = (I−KH)P` loses symmetry over time | Joseph form: `(I−KH)P(I−KH)ᵀ + KRKᵀ` |
| 4 | CV filter | `logNIS()` opened/closed file every update | Persistent `std::ofstream nis_log_` member |
| 5 | CTRV filter | `std::vector<Eigen::VectorXd>` sigma points → heap alloc at 1000 Hz | Fixed-size `Eigen::Matrix` member buffers |
| 6 | CTRV filter | UKF weights recomputed every call | Promoted to `static constexpr` |
| 7 | CTRV filter | `logNIS()` opened/closed file every update | Persistent `std::ofstream nis_log_` member |
| 8 | ESKF | F matrix ambiguity: `-I3` placed in middle block (accel bias) | Corrected to last block (gyro bias): `F.block<3,3>(0,6) = -I3` |
| 9 | ESKF | Naive `P = (I−KH)P` in `updateGravity()` | Joseph form applied |
| 10 | ESKF | `sigma_accel_meas_` missing; process noise `sigma_a` used for meas noise | Added dedicated `sigma_accel_meas_` member |
| 11 | ESKF | `logNIS()` opened file per call | Persistent `nis_log_` member opened in `initialize()` |
| 12 | ZARU | `getH()` risk of placing `I3` in middle block (accel bias) | `H.block<3,3>(0,6) = I3` — gyro bias in last block |
| 13 | Sage-Husa | Eigendecomposition before symmetrization | Symmetrize first: `0.5*(R + Rᵀ)`, then eigen-decompose |
| 14 | Sage-Husa | No eigenvalue floor on `R_hat_` | `R_hat_ += (floor − min_eig) * I` when below floor |
| 15 | NIS validation | Crash on empty CSV | Guard: `if total == 0: sys.exit(1)` |
| 16 | NIS validation | Exit code ambiguity | Always exit 0 unless gate fails **and** `--fail-on-violation` |
| 17 | CI | `nis_camera_zaru.csv` risk of accidental CI gating | Explicit exclusion with comment in `ci.yml` |
| 18 | CI | NIS gate jobs could run on failed build | `needs: build` on both NIS gate jobs |
| 19 | CTRV | `ctrvPredictSingle` with `Eigen::VectorXd` argument copies | Changed to `Eigen::Ref<const State5d>` |
| 20 | CV filter | `H_` initialized as zero, position block never set explicitly | Explicit `H_.block<3,3>(0,0) = I3` in constructor |

---

## Full Design Document

[GHOST_V10.md](GHOST_V10.md) — complete architecture, filter derivations, hardware integration notes, MAVLink bridge design, and simulation configuration.

---

## Real-World Relevance

| Application | Connection |
|---|---|
| Counter-drone intercept | Anduril Anvil — GPS-denied terminal guidance against maneuvering target |
| Underground navigation | Shield AI Nova 2 — vision-only target tracking in tunnels |
| Ship deck landing | Shield AI V-BAT — kinematic target model for moving deck |
| EW-jammed environments | GPS spoofed/denied — vision + kinematic fallback |


