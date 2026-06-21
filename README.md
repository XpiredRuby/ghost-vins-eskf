# GHOST — GPS-Denied Hardware Occlusion-Survivable Tracker

> A dual-filter GPS-denied target tracker running on a Raspberry Pi 4B: a 9-state attitude ESKF stabilizes the camera platform frame while a CV/CTRV kinematic filter tracks an RC car and coasts through occlusions using its own velocity estimate.

**Author:** Vinayak Manoj Nair — Texas A&M University, B.S. Aerospace Engineering (Dec 2026)  
**Repo:** `ghost-vins-eskf` | **Status:** V12 USB UVC baseline — 20 engineering flaws documented and fixed — code complete

**Current spec:** [GHOST_V12_USB_WEBCAM.md](GHOST_V12_USB_WEBCAM.md)  
**Legacy spec (CSI/IMX296):** [GHOST_V10.md](GHOST_V10.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CAMERA PLATFORM (static tripod)                 │
│                                                                     │
│  [ICM-42688-P]──SPI 1000Hz + DRDY ISR──┐                           │
│  [MPU-6050]────I2C  400Hz + DRDY ISR──┤                           │
│  [USB UVC]─────V4L2 /dev/video0────────┤                           │
│  (OOSM rollback for camera-IMU sync)──┘                           │
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

**V12 baseline camera:** USB UVC webcam via V4L2. Camera–IMU time alignment uses measured pipeline latency and ESKF OOSM rollback — not hardware strobe sync. Optional future work: IMX296 global shutter + GPIO22 strobe (see V12 spec §Optional Hardware Upgrade).

---

## Hardware

| Component        | Part                                  | Role                              |
|------------------|---------------------------------------|-----------------------------------|
| Compute          | Raspberry Pi 4B 4GB                   | Runs both filters at full rate    |
| Camera (baseline)| USB UVC webcam (720p/1080p)           | AprilTag detection + optical flow |
| Primary IMU      | ICM-42688-P SPI breakout              | 1000 Hz attitude ESKF input       |
| Watchdog IMU     | MPU-6050 I2C breakout                 | 100 ms disagreement fault flag    |
| RC Car           | 1:20 scale, flat roof                 | Tracked target                    |
| AprilTag         | 36h11 tag0, 10 cm × 10 cm laminated   | Vision measurement source         |
| Occlusion object | Shoebox                               | Occlusion test scenario           |

**Budget: ~$170–$190 total.** No Pixhawk, no GPS — guidance closes over UDP MAVLink to PX4 SITL.

**Optional future work:** innomaker IMX296 CSI global-shutter camera + GPIO22 strobe ISR for sub-millisecond hardware timestamp sync (Phase 5 in V12 spec). Not required for baseline bring-up.

---

## The Two Filters

### Filter 1 — 9-State Attitude ESKF (`src/attitude_filter/`)

Runs at **1000 Hz**, driven by the ICM-42688-P IMU over SPI.

Estimates the camera platform's orientation as a quaternion (`q_cam`) plus accelerometer bias (`b_a`) and gyro bias (`b_g`). The output rotation matrix `R_cam_to_NED` is used by Filter 2 to convert AprilTag detections from camera frame into NED world coordinates.

Vision updates arrive on V4L2 buffer timestamps with measured pipeline latency; the ESKF OOSM rollback buffer time-aligns them with IMU states.

**Three update mechanisms:**
- **Gravity update** — uses the accelerometer reading as a gravity direction measurement when the platform is not accelerating. Produces NIS logged to `logs/nis_camera_gravity.csv` (CI-gated at χ²(3), 95%).
- **ZARU (Zero Angular Rate Update)** — fires at 1 Hz on a static platform; treats the absence of angular rate as a pseudo-measurement to correct gyro bias. NIS logged to `logs/nis_camera_zaru.csv` (*not* CI-gated — ZARU is static-platform only).
- **Sage-Husa adaptive noise** — recursively updates the measurement noise estimate R̂ with a forgetting factor of 0.98; enforces positive definiteness via eigenvalue floor.

### Filter 2 — CV/CTRV Kinematic Filter (`src/target_tracker/`)

Runs at the **vision frame rate** (~20–30 fps on USB UVC baseline).

Tracks the RC car's 2-D floor position and velocity. Two parallel models:

- **CV (Constant Velocity)** — 6-state `[px, py, pz, vx, vy, vz]`. EKF with linear state transition and Singer model process noise. Observes position from the AprilTag pose.
- **CTRV (Constant Turn Rate and Velocity)** — 5-state `[px, py, v, ψ, ψ̇]`. UKF with nonlinear sigma-point propagation. Singularity guard fires at `|ψ̇| < 1e-4 rad/s`, reverting to CV straight-line equations.

**IMU data never enters this filter.** The IMU is mounted on the static tripod, not the moving car. During occlusion the filter simply propagates its kinematic model forward. NIS logged to per-filter CSV files (CI-gated — see CI Pipeline).

---

## Repository Structure

```
ghost-vins-eskf/
├── README.md
├── GHOST_V12_USB_WEBCAM.md               # Current design document (V12)
├── GHOST_V10.md                          # Legacy CSI/IMX296 design document
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml                        # NIS-gated CI pipeline
├── config/
│   ├── camera.yaml                       # USB UVC parameters
│   ├── imu.yaml
│   ├── filter.yaml
│   └── guidance.yaml
├── src/
│   ├── attitude_filter/                  # Filter 1 — 9-state ESKF
│   ├── target_tracker/                   # Filter 2 — CV/CTRV
│   ├── imu_driver/
│   ├── guidance/
│   ├── mavlink_bridge/
│   └── ros2_nodes/                       # vision_node, eskf_node, tracker_node, …
├── analysis/
│   └── nis_validation.py                 # NIS χ² gate (CLI tool)
├── test/
│   ├── test_eskf.cpp
│   └── test_pronav.cpp
└── logs/                                 # Runtime-generated — not committed
    ├── nis_camera_gravity.csv
    ├── nis_camera_zaru.csv
    ├── nis_cv_tracker.csv
    └── nis_ctrv_tracker.csv
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

ROS2 nodes (`vision_node`, etc.) require additional Pi-side dependencies — see [GHOST_V12_USB_WEBCAM.md](GHOST_V12_USB_WEBCAM.md) §Vision Pipeline and `CMakeLists.txt`.

---

## Run the NIS CI Gate Locally

After a recording session, NIS logs are written to `logs/`. Validate them against the χ² distribution at 95% confidence:

```bash
# Attitude filter — gravity update NIS
python3 analysis/nis_validation.py \
  --log logs/nis_camera_gravity.csv \
  --dof 3 \
  --confidence 0.95 \
  --fail-on-violation

# CV target tracking filter NIS
python3 analysis/nis_validation.py \
  --log logs/nis_cv_tracker.csv \
  --dof 3 \
  --confidence 0.95 \
  --fail-on-violation

# CTRV target tracking filter NIS
python3 analysis/nis_validation.py \
  --log logs/nis_ctrv_tracker.csv \
  --dof 2 \
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
3. **`nis_gate_cv`** — validates `logs/nis_cv_tracker.csv` (needs `build`).
4. **`nis_gate_ctrv`** — validates `logs/nis_ctrv_tracker.csv` (needs `build`).

`nis_camera_zaru.csv` is deliberately excluded from CI gating — ZARU is a static-platform-only pseudo-measurement, not valid during dynamic rosbag replay.

---

## Engineering Decisions and Documented Fixes

Twenty implementation flaws were identified and corrected during development. V12 reclassifies flaw #14 (camera timestamp): baseline fix is measured pipeline latency + OOSM rollback; IMX296 strobe ISR is optional Phase 5 upgrade.

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

Full V12 context for camera timestamping: [GHOST_V12_USB_WEBCAM.md](GHOST_V12_USB_WEBCAM.md) §Vision Pipeline, §20 Engineering Flaws.

---

## Design Documents

| Document | Status |
|---|---|
| [GHOST_V12_USB_WEBCAM.md](GHOST_V12_USB_WEBCAM.md) | **Current** — USB UVC baseline, phases, V&V, FMEA, evidence pack |
| [GHOST_V10.md](GHOST_V10.md) | **Legacy** — CSI/IMX296 global shutter + strobe timing reference |

---

## Real-World Relevance

| Application | Connection |
|---|---|
| Counter-drone intercept | Anduril Anvil — GPS-denied terminal guidance against maneuvering target |
| Underground navigation | Shield AI Nova 2 — vision-only target tracking in tunnels |
| Ship deck landing | Shield AI V-BAT — kinematic target model for moving deck |
| EW-jammed environments | GPS spoofed/denied — vision + kinematic fallback |
| Commodity vision | USB UVC baseline — plug-and-play field sensors without CSI integration |
