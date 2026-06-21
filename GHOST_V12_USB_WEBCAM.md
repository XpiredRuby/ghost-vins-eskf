# GHOST — GPS-Denied Hardware Occlusion-Survivable Tracker (V12)

**Owner:** Vinayak Manoj Nair  
**University:** Texas A&M University — B.S. Aerospace Engineering (Dec 2026)  
**Target Roles:** GNC Engineer · Autonomy Engineer · Navigation Engineer  
**Target Companies:** Anduril · Shield AI · Skydio · JPL · Draper Laboratory  
**GitHub:** `ghost-vins-eskf`  
**Status:** V12 pivot — USB UVC webcam baseline; dual-filter code complete; hardware bring-up in progress  
**Last Updated:** June 2026  
**Supersedes:** [GHOST_V10.md](GHOST_V10.md) (legacy CSI/IMX296 spec — retained for reference only)

---

## V12 Pivot Summary

| Area | V10 (legacy) | V12 (current) |
|---|---|---|
| Baseline camera | innomaker IMX296 CSI global shutter | USB UVC webcam (V4L2) |
| Timestamp sync | IMX296 Strobe → GPIO22 ISR | V4L2 buffer timestamp + ESKF OOSM rollback buffer |
| Procurement blocker | CSI module availability / libcamera BSP | Standard UVC — plug-and-play on Pi 4B |
| Rolling shutter | Not applicable (global shutter) | Operating envelope + exposure/speed limits |
| IMX296 / strobe | Required | **Optional future work** — see §Optional Hardware Upgrade |

The estimation architecture is unchanged: Filter 1 (9-state attitude ESKF) and Filter 2 (CV/CTRV kinematic tracker) remain separate by the strapdown constraint. Only the vision front-end and camera-IMU time alignment strategy changed for the baseline platform.

---

## What GHOST Does

A USB webcam and IMU on a static tripod watch an RC car moving on the floor. A Raspberry Pi 4B runs two simultaneous estimation filters: a 9-state attitude ESKF that stabilizes the camera platform frame, and a CV/CTRV kinematic filter that tracks the RC car and predicts its motion during occlusion. Guidance commands go over UDP MAVLink from the Pi to PX4 SITL on a laptop. A simulated drone in Gazebo Fortress receives ProNav acceleration setpoints and intercepts the car.

When the car drives behind a shoebox and the camera loses the AprilTag, the tracking filter coasts on its own velocity estimate. The IMU's only role during occlusion is detecting camera platform disturbances — it does not propagate car motion. When the car re-emerges, vision corrects the filter drift.

Everything runs on real ARM hardware with real sensor noise. No GPS. No simulation shortcuts on the estimation side.

**Framing:** Defense-grade GPS-denied estimation and target tracking on a sub-$200 ARM platform with commodity USB vision. Pixhawk hardware deliberately eliminated — guidance closes over UDP MAVLink to PX4 SITL, identical interface to hardware, zero procurement dependency.

---

## Real-World Relevance

| Application | Connection |
|---|---|
| Counter-drone intercept | Anduril Anvil — GPS-denied terminal guidance against maneuvering target |
| Underground navigation | Shield AI Nova 2 — vision-only target tracking in tunnels |
| Ship deck landing | Shield AI V-BAT — kinematic target model for moving deck |
| EW-jammed environments | GPS spoofed/denied — vision + kinematic fallback |
| Commodity vision stacks | USB UVC baseline mirrors field-deployable plug-and-play sensors |

---

## Hardware

| Component | Part | Status | Notes |
|---|---|---|---|
| Compute | Raspberry Pi 4B 4GB | 📦 In transit | PREEMPT_RT for IMU DRDY ISR |
| **Camera (baseline)** | **USB UVC webcam** (720p/1080p, MJPEG or YUYV) | ✅ Baseline | `/dev/video0` via V4L2; no CSI ribbon required |
| Primary IMU | ICM-42688-P SPI breakout | 🛒 Arriving | 1000 Hz attitude ESKF input |
| Watchdog IMU | MPU-6050 I2C breakout | ⏳ Checking | Fault flag only — never enters Filter 2 |
| Power meter | YEREADW KWS-2303C USB-C | 🛒 Arriving | Power budget characterization |
| Jumper wires | Female-to-Female 20cm 40-pack | ⏳ Checking | SPI + GPIO wiring |
| RC Car | 1:20 scale, flat roof | Order after system verified | Speed limited for rolling shutter |
| AprilTag | 36h11 tag0, 10cm×10cm, laminated | Print at library | Vision measurement source |
| Shoebox | Physical occlusion obstacle | Already own | Occlusion V&V scenario |

**Budget: ~$170–$190 total** (USB webcam ~$15–$35; Pixhawk eliminated — saves $31–$110)

**Optional future work (not required for V12 baseline):**

| Component | Part | Purpose |
|---|---|---|
| Global-shutter CSI camera | innomaker IMX296 (or equivalent) | Sub-3 ms exposure, no rolling-shutter skew |
| Strobe GPIO wiring | IMX296 Strobe → GPIO22 ISR | Hardware shutter-open timestamp < 50 µs jitter |

**What NOT to buy for V12 baseline:**
- IMX296 or CSI ribbon — optional upgrade only
- ICM-20689 — discontinued globally
- Any physical flight controller — pure SITL over UDP
- Pi 5 — PREEMPT_RT not yet stable on Pi 5
- IMU without DRDY pin — hardware timestamping requires it
- 1:10 or larger RC car — too fast for rolling-shutter envelope

---

## Repository Structure

```
ghost-vins-eskf/
├── README.md
├── GHOST_V12_USB_WEBCAM.md          # Current spec (this document)
├── GHOST_V10.md                     # Legacy CSI/IMX296 spec
├── .github/workflows/ci.yml         # NIS-gated CI pipeline
├── config/
│   ├── camera.yaml                  # USB UVC parameters
│   ├── imu.yaml
│   ├── filter.yaml
│   └── guidance.yaml
├── src/
│   ├── attitude_filter/             # Filter 1 — 9-state ESKF
│   ├── target_tracker/              # Filter 2 — CV/CTRV
│   ├── imu_driver/
│   ├── guidance/
│   ├── mavlink_bridge/
│   └── ros2_nodes/                  # vision_node, eskf_node, tracker_node, …
├── analysis/
│   └── nis_validation.py
├── test/
└── logs/                            # Runtime generated — not committed
```

---

## Full System Architecture

```
CAMERA PLATFORM (static tripod)
  [ICM-42688-P]  --SPI 1000Hz + DRDY GPIO17 (PREEMPT_RT < 50μs)-->  [Pi 4B 4GB]
  [MPU-6050]     --I2C 400Hz  + DRDY GPIO27 (watchdog only)      -->  [Pi 4B 4GB]
  [USB UVC]      --/dev/video0 V4L2 (640×480 or 1280×720)        -->  [Pi 4B 4GB]
                              ↳ buffer timestamp → OOSM rollback in ESKF

TARGET
  [AprilTag 36h11 10cm×10cm on RC car] --camera--> [Vision Pipeline on Pi]

SIMULATION (Gazebo Fortress)
  [Pi 4B] --WiFi UDP:14540--> [Laptop: PX4 SITL + Gazebo Fortress]
  [a_cmd(NED)] --SET_POSITION_TARGET_LOCAL_NED mask 0b0000110000111111--> [PX4]
```

### Data Flow

```
=== FILTER 1: ATTITUDE FILTER (9-state ESKF) ===
ICM-42688-P (SPI 1000Hz + DRDY ISR)
MPU-6050    (I2C 400Hz  + DRDY ISR, watchdog only)
    → Timestamp-aligned on hardware interrupt times
        → 9-state ESKF @ 1000Hz → R_cam_to_NED, b_a, b_g
        → OOSM rollback buffer absorbs measured vision pipeline latency
        → MPU-6050 attitude → 100ms moving window disagreement → fault flag

=== FILTER 2: TARGET TRACKING FILTER (CV/CTRV) ===
USB UVC (V4L2)
    → Capture at configured resolution (640×480 baseline; 1280×720 optional)
        → Tier 1: full frame if no prior detection
        → Tier 2: 300×300 ROI at predicted pixel (K scaled to capture resolution)
            → AprilTag detector (≥20fps full frame, ≥30fps ROI target on Pi 4B)
                → pose in camera frame → NED via R_cam_to_NED
                    → visible:  measurement update to CV/CTRV filter
                    → occluded: CV or CTRV kinematic propagation (no IMU)
    → LK optical flow between detections (planned)

Output: x_target(NED) = [p_x, p_y, v, psi, psi_dot]^T

=== GUIDANCE (TPN in NED) ===
x_drone(Gazebo ENU) → R_ENU_to_NED → x_drone(NED)
x_target_scaled - x_drone → delta_x_rel (Z = 0 exactly)
    → TPN: a_cmd = N · Omega × V_c
        → SET_POSITION_TARGET_LOCAL_NED → UDP:14540 → PX4 SITL
```

---

## Vision Pipeline (USB UVC Baseline)

```
USB UVC webcam — V4L2 capture
  Device:     /dev/video0 (configurable in camera.yaml)
  Format:     MJPEG or YUYV — prefer MJPEG for USB bandwidth headroom
  Resolution: 640×480 @ 30 fps (baseline) or 1280×720 @ 15–30 fps
  Exposure:   Short as practicable; RC car speed limited for rolling shutter

Frame processing:
  1. V4L2 dequeue → Y/grayscale plane for AprilTag
  2. Optional decimation if native resolution exceeds processing budget
  3. K_scaled = K_intrinsic adjusted for any resize/decimation
  4. Tier 1: full frame if no prior detection
  5. Tier 2: 300×300 ROI at predicted pixel — project with K_scaled

Camera-IMU timestamp sync (baseline):
  V4L2 buffer timestamps arrive 15–40 ms after shutter on rolling-shutter UVC webcams.
  Fix: measure pipeline latency in Phase 2; ESKF OOSM rollback buffer (500 ms circular)
  rolls back to the IMU state at the image timestamp, applies vision update, re-propagates.
  Do NOT assume latency — measure it.

Rolling-shutter operating envelope (V12 baseline constraint):
  Tag size: 10 cm × 10 cm minimum
  Range: 0.5–3.0 m
  Max oblique angle: < 45°
  Min illumination: > 50 lux
  Max RC car speed: characterized in Phase 2 — stay within reprojection gate
  All demos run within measured bounds — not assumptions
```

---

## Optional Hardware Upgrade — IMX296 Global Shutter + Strobe

Not required for V12 baseline. Pursue only after USB UVC pipeline, dual filters, and guidance demo are validated.

```
IMX296 Global Shutter — 1456×1088 native (CSI / libcamera)
  Exposure: < 3 ms — eliminates rolling-shutter skew
  Decimate ÷2 → 728×544 for AprilTag throughput

Hardware timestamp upgrade:
  IMX296 Strobe pin → GPIO22 ISR → CLOCK_MONOTONIC at shutter-open
  Replaces V4L2 userspace timestamp; camera-IMU delta target < 1 ms (VV-23b)
  vision_node retains libcamera + strobe code path for this upgrade
```

See [GHOST_V10.md](GHOST_V10.md) §Vision Pipeline for IMX296-specific integration notes.

---

## IMU Driver

Unchanged from V10 — see [GHOST_V10.md](GHOST_V10.md) §IMU Driver for register maps, Allan Variance procedure, and watchdog logic.

V12 note: baseline camera-IMU alignment uses **measured pipeline latency + OOSM**, not strobe GPIO. Strobe GPIO configuration in `config/camera.yaml` is disabled by default (`strobe_enabled: false`).

---

## Development Phases

### Phase 1 — OS + Drivers
| Task | Exit Criteria |
|---|---|
| Flash Ubuntu 22.04.5 Server | Boots on Pi |
| Install PREEMPT_RT kernel | `uname` shows PREEMPT_RT |
| Enable SPI, configure GPIO | `/dev/spidev0.0` present |
| ICM-42688-P SPI driver | WHO_AM_I = 0x47, 1000 Hz verified |
| DRDY ISR + CLOCK_MONOTONIC timestamp | Jitter < 50 µs over 1000 samples |
| **USB UVC V4L2 bring-up** | **`v4l2-ctl --list-devices`; stable 640×480 MJPEG stream** |
| MPU-6050 I2C driver | 400 Hz verified |
| Dual DRDY hardware interrupt timestamping | Both ISRs active simultaneously |
| 4-hour Allan Variance run | ARW + Bias Instability measured |
| Verify ZARU — yaw drift < 1° over 5-min static run | VV-25 |
| Watchdog threshold characterization | Zero false positives in 10-min run |

### Phase 2 — Vision + Calibration
| Task | Exit Criteria |
|---|---|
| USB webcam intrinsic calibration | Reprojection error < 0.5 px |
| Extrinsic calibration (R_cam_to_NED) | AprilTag at known position → NED residual < 2 cm (VV-18) |
| **Measure vision pipeline latency** | **Logged mean + 99th percentile — feeds OOSM buffer (VV-23)** |
| AprilTag detector on configured frame | ≥ 20 fps full frame on Pi 4B |
| ROI Tier 2 — scaled K projection | ≥ 30 fps ROI, correct crop region |
| LK optical flow between detections | Stable feature tracks |
| Sim-to-reality transform calibration | K_sim, R_align, t_origin_offset (VV-19) |
| Rolling-shutter speed envelope | Document max RC car speed at measured reprojection gate |

### Phase 3 — Dual Filter + Occlusion
| Task | Exit Criteria |
|---|---|
| 9-state attitude ESKF with OOSM | Vision updates time-aligned via rollback |
| CV target tracking filter | 6-state, separate ROS2 node |
| CTRV model (UKF) | Turning occlusion handled |
| Verify ZARU active — yaw drift < 1° over 5-min | VV-25 |
| Measure RC car a_max | Q_target from Singer model |
| CV vs CTRV model comparison | Lower NIS model selected |
| Straight-line shoebox occlusion test | CV coast works, drift measured |
| Turning shoebox test | CTRV handles it |
| All NIS CI gates passing | VV-21 |
| 10× rosbag replay | Consistent output |

### Phase 4 — Guidance + Benchmark + Demo
| Task | Exit Criteria |
|---|---|
| Verify UDP MAVLink connectivity | Pi → Laptop PX4 SITL heartbeat confirmed |
| PX4 SITL + Gazebo Fortress integration | Drone responds to SET_POSITION_TARGET_LOCAL_NED |
| ProNav with K_sim and r_cutoff terminal coast | Clean intercept — no spiral (VV-24) |
| Z-floor constraint | Drone holds altitude ≥ z_floor_min (VV-17) |
| VINS-Mono benchmark | Drift overlay comparison |
| Demo video 60–90 s | Intercept → occlusion → coast → reacquisition |
| GitHub v1.0.0 tagged | README with all measured numbers |

### Phase 5 — Optional IMX296 Upgrade (Future Work)
| Task | Exit Criteria |
|---|---|
| IMX296 CSI + libcamera bring-up | 728×544 decimated stream stable |
| GPIO22 strobe ISR | Camera-IMU timestamp delta < 1 ms (VV-23b) |
| Compare OOSM vs hardware-sync NIS | Document improvement — not required for baseline sign-off |

---

## V&V Matrix

| ID | Requirement | Method | Status |
|---|---|---|---|
| VV-11 | CV filter predicts straight-line occlusion position | Shoebox test | TBD |
| VV-12 | CV occlusion valid for straight-line only | Documented constraint | TBD |
| VV-13 | CTRV handles constant-radius turns | Turning shoebox test | TBD |
| VV-14 | IMM handles unknown maneuver type | IMM NIS comparison | Optional |
| VV-17 | Gazebo drone altitude ≥ z_floor_min during intercept | Altitude log | TBD |
| VV-18 | AprilTag at known position → NED residual < 2 cm | Drive-to-point test | TBD |
| VV-19 | Sim-to-reality transform — car at known position → Gazebo projection < 5 cm | Drive-to-point | TBD |
| VV-20 | Drone flies toward target (not spiral) — ENU/NED correct | Trajectory log | TBD |
| VV-21 | NIS gates pass on reference rosbag | CI pipeline | TBD |
| VV-22 | PnP depth within 5% at known distance | Calibration test | TBD |
| **VV-23** | **Measured vision pipeline latency bounded; OOSM rollback validated** | **Latency log + ESKF consistency** | **TBD** |
| VV-23b | Camera-IMU timestamp delta < 1 ms with strobe ISR (optional upgrade) | Strobe ISR active | Optional |
| VV-24 | Clean intercept — no spiral in final 1.5 m | Trajectory log | TBD |
| VV-25 | Yaw drift < 1° over 5-minute static run (ZARU active) | Attitude log | TBD |
| VV-26 | Rolling-shutter reprojection gate holds at characterized max RC speed | Speed sweep | TBD |

---

## FMEA

| Failure Mode | Effect | Detection | Mitigation |
|---|---|---|---|
| SPI DRDY line not wired | IMU data lost | No data published | Verify GPIO17 continuity before power-on |
| PREEMPT_RT not installed | Jitter > 1 ms | Timestamp variance test | `uname` check in setup script |
| ICM-42688-P WHO_AM_I wrong | Wrong register map used | Read 0x47 at startup | Startup assertion — halt if not 0x47 |
| USB webcam not enumerated | No vision | `/dev/video0` missing | `v4l2-ctl --list-devices`; try alternate USB port |
| UVC bandwidth saturation | Frame drops, tracker coasts | FPS monitor | MJPEG mode; reduce resolution to 640×480 |
| **Rolling-shutter motion blur** | **Bad PnP, NIS spike** | **Reprojection error gate** | **Limit RC car speed; shorten exposure; VV-26 envelope** |
| **V4L2 timestamp latency assumed not measured** | **OOSM misaligned, ESKF drift** | **Camera-IMU innovation bias** | **Measure latency Phase 2; OOSM rollback buffer** |
| Sage-Husa R goes negative definite | Filter diverges | NIS spike, P blowup | Eigenvalue floor clamp after every update |
| ZARU H matrix uses middle block | Accel bias updated with gyro measurement | VV-25 yaw drift fails | H_ZARU = [0,0,I] — last block (gyro bias) |
| K_intrinsic used on resized frame | ROI crops wrong location | ROI hit rate drops | K_scaled for every resize/decimation |
| ENU/NED mismatch in delta_x_rel | ProNav spiral divergence | Drone flies away | R_ENU_to_NED applied before every ProNav update |
| ProNav terminal singularity | Drone flips at intercept | LOS rate spike | r_cutoff_meters terminal coast (default 1.5 m) |
| CV model during turning occlusion | Filter projects car through wall | NIS spike at reacquisition | CTRV model |
| Watchdog raw threshold | Vibration floods false positives | Constant fault flags | 100 ms moving window on attitude disagreement |

**Optional upgrade FMEA entries (IMX296 path):**

| Failure Mode | Effect | Detection | Mitigation |
|---|---|---|---|
| V4L2 timestamp used without OOSM on CSI path | 15–40 ms offset corrupts ESKF | Camera-IMU delta > 1 ms | IMX296 Strobe → GPIO22 ISR (Phase 5) |
| libcamera BSP mismatch | Camera fails to start | `vision_node` init error | Pin libcamera version; see GHOST_V10.md |

---

## Evidence Pack (V12 Baseline Sign-Off)

Artifacts required before declaring V12 baseline complete. Store under `logs/` and `docs/evidence/` (not committed — local only).

| Artifact | Contents | Phase |
|---|---|---|
| `evidence/allan_variance/` | 4-hour static IMU log + ARW/BI plots | 1 |
| `evidence/camera_cal/` | Intrinsic/extrinsic calibration report, reprojection < 0.5 px | 2 |
| `evidence/latency/` | Vision pipeline latency mean, σ, 99th percentile | 2 |
| `evidence/nis/` | `nis_camera_gravity.csv`, `nis_cv_tracker.csv`, `nis_ctrv_tracker.csv` passing CI gates | 3 |
| `evidence/occlusion/` | Shoebox straight + turning rosbag + drift plots | 3 |
| `evidence/guidance/` | Gazebo intercept trajectory, VV-24 terminal coast log | 4 |
| `evidence/demo/` | 60–90 s demo video: intercept → occlusion → coast → reacquisition | 4 |
| `evidence/vv_matrix/` | Completed V&V table with measured pass/fail numbers | 4 |

---

## NIS-Gated CI Pipeline

Unchanged — see `.github/workflows/ci.yml` and [README.md](README.md). ZARU NIS remains logged but not CI-gated.

---

## 20 Engineering Flaws — V12 Notes

Flaws 1–20 from V10 remain valid. V12-specific reclassification:

| # | V10 fix | V12 baseline | Optional upgrade |
|---|---|---|---|
| 14 | IMX296 Strobe → GPIO22 ISR | **Measured latency + OOSM rollback** | Strobe ISR (Phase 5) |
| 12 | Decimate 1456×1088 ÷2 | **640×480 UVC or scaled capture** | IMX296 decimation path |

Full flaw table: [GHOST_V10.md](GHOST_V10.md) §20 Engineering Flaws.

---

## Critical Rules — V12 Additions

| Rule | Why |
|---|---|
| Never assume vision pipeline latency | OOSM buffer size must come from measured Phase 2 data |
| Never require IMX296 for baseline demo | USB UVC is the V12 procurement path |
| Never exceed characterized RC car speed on rolling shutter | Motion blur breaks PnP — VV-26 |
| Never disable OOSM on V4L2 timestamps | 15–40 ms skew is real on UVC webcams |

All V10 critical rules still apply unless superseded above.

---

## Interview Q&A — V12 Camera Sync Answer

**"How did you synchronize camera and IMU timestamps on a USB webcam?"**

> V4L2 timestamps images when the buffer arrives in userspace — typically 15–40 ms after
> exposure on a rolling-shutter UVC camera, and variable per frame. My IMU is hardware-timestamped
> at < 50 µs via DRDY ISR. Rather than trusting the V4L2 stamp as ground truth, I measure the
> pipeline latency in Phase 2 and use the ESKF's OOSM rollback buffer: roll back to the IMU
> state at the image time, apply the vision update, then re-propagate forward. For a future
> global-shutter upgrade I have a GPIO22 strobe ISR path designed — that is optional Phase 5 work,
> not a baseline blocker.

---

## Resume Bullet (V12)

```
GHOST: GPS-Denied Occlusion-Survivable Target Tracker | C++ · ROS2 · Eigen · OpenCV

• Architected dual-filter GPS-denied system on ARM Cortex-A72: 9-state attitude ESKF for
  camera platform + CV/CTRV kinematic filter for RC car — strapdown separation enforced;
  desk IMU cannot propagate car motion.

• Pivoted vision front-end to commodity USB UVC baseline (~$20) with measured pipeline-latency
  compensation via ESKF OOSM rollback — sub-$200 platform, no CSI procurement dependency.

• Documented and resolved 20 engineering flaws including ProNav coordinate mismatches,
  terminal guidance singularity, ZARU H-matrix axis error, and NIS stream contamination.

• Automated dual NIS chi² CI gate — both filters validated on reference rosbag; PRs rejected
  on filter consistency regression.

• Eliminated Pixhawk hardware: guidance closes over UDP MAVLink to PX4 SITL — identical
  MAVLink interface, zero hardware failure modes.
```

---

*Last updated: June 2026*  
*Status: V12 USB UVC baseline — code complete, hardware bring-up in progress*  
*Legacy spec: [GHOST_V10.md](GHOST_V10.md)*
