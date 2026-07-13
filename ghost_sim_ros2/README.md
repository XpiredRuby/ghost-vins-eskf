# GHOST ROS 2 Package

## Complete GPS-denied drone/robot mission

The recommended software demo is now the complete intended GHOST mission—not the legacy oval/dropout generator:

```bash
ros2 launch ghost_sim_ros2 ghost_drone_mission.launch.py
```

Open `http://<RASPBERRY_PI_IP>:8088` for the live 2D mission dashboard.

The demo runs a mobile observer, camera range/FOV/obstacle line-of-sight sensing, formal IMM and GHOST-MH prediction, bounded hidden-target guidance, named-obstacle vantage selection, inflated-obstacle A* planning, collision checks, and measured reacquisition acceptance.

Final deterministic acceptance:

| Metric | Value |
|---|---:|
| Mission duration | `32.0816 s` |
| Obstacle LOS losses | `2` |
| Longest LOS loss | `9.5332 s` |
| IMM outputs during occlusion | `456` |
| GHOST-MH outputs during occlusion | `457` |
| Reacquisitions | `2` |
| Observer travel | `12.3016 m` |
| Collisions / boundary violations | `0 / 0` |
| Overall result | **PASS** |

- [Mission software and architecture](docs/GHOST_DRONE_MISSION_SOFTWARE.md)
- [Implementation and validation report](docs/GHOST_DRONE_MISSION_IMPLEMENTATION_REPORT.md)
- [Machine-readable validation](docs/GHOST_DRONE_MISSION_VALIDATION.json)

The observer's own pose is supplied by the local software simulator. This is not a SLAM/VIO, PX4, HIL, or real-flight claim.

## Scope

`ghost_sim_ros2` contains the active ROS 2 Jazzy target-estimation package, deterministic software-in-the-loop GNC harness, hardware replay, physical-validation tools, campaign operations, analysis, and public documentation for Project GHOST.

The active hardware sensor path is:

```text
AprilTag target
  -> standard USB UVC webcam
  -> Linux V4L2 on Raspberry Pi
  -> /ghost/vision/target_pose
  -> formal IMM and heuristic GHOST-MH trackers
```

The package also includes a software-only synthetic measurement path for development and regression testing. Simulation topics and bridge outputs are not evidence that a real vehicle is commanded.

## Portfolio snapshot

### Preserved hardware behavior

Run: `live_camera_calibrated_R_01`

| Metric | Value |
|---|---:|
| Duration | `48.28 s` |
| Vision measurements | `655` |
| USB-camera pose rate | `13.57 Hz` |
| IMM odometry rate | `30.01 Hz` |
| MH odometry rate | `29.99 Hz` |
| Maximum IMM prediction-only steps | `77` |
| Maximum IMM measurement age | `2.849 s` |

This validates the USB-camera-to-ROS-to-tracker pipeline, publication behavior, dropout-state telemetry, prediction-only propagation, and reacquisition. It does not validate physical tracking accuracy.

### Deterministic formal-IMM GNC SIL

The repository's actual formal IMM drives relative-standoff guidance, acceleration-limited control, actuator lag, follower dynamics, and a `TRACKING` / `PREDICTION` / `SAFE_HOLD` supervisor.

| Scenario | Final standoff error | Maximum estimator error | Safe hold |
|---|---:|---:|---:|
| nominal visible | `0.00114 m` | `0.02673 m` | `0.0 s` |
| short dropout | `0.000353 m` | `0.16357 m` | `0.0 s` |
| long dropout | `0.00986 m` | `0.41683 m` | `2.0 s` |

These are deterministic synthetic-truth SIL results—not PX4, HIL, vehicle, or flight results.

## Direct review paths

- [Public showcase](https://xpiredruby.github.io/ghost-vins-eskf/)
- [Interactive hardware replay](https://xpiredruby.github.io/ghost-vins-eskf/demo.html)
- [USB hardware & BOM](https://xpiredruby.github.io/ghost-vins-eskf/hardware.html)
- [`docs/GHOST_PROJECT_REPORT.md`](docs/GHOST_PROJECT_REPORT.md)
- [`docs/GHOST_PORTFOLIO_PACKET.md`](docs/GHOST_PORTFOLIO_PACKET.md)
- [`docs/GHOST_HARDWARE_FREE_COMPLETION.md`](docs/GHOST_HARDWARE_FREE_COMPLETION.md)
- [`docs/GHOST_PHYSICAL_VALIDATION_MASTER_RUNBOOK.md`](docs/GHOST_PHYSICAL_VALIDATION_MASTER_RUNBOOK.md)
- [`docs/GHOST_CAREER_SNIPPETS.md`](docs/GHOST_CAREER_SNIPPETS.md)

## Build

From the ROS 2 workspace root:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2 --symlink-install
source install/setup.bash
```

## Software-only tracker pipeline

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

Optional:

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py \
  noise_std_m:=0.04 \
  dropout_duration_s:=5.0
```

This launches synthetic measurements, the CV tracker, evidence logging, and target-state bridge topics. It does not arm or control a vehicle.

## Formal IMM and GHOST-MH live outputs

```text
/ghost/tracker_imm/target_odom
/ghost/tracker_imm/futures_json
/ghost/tracker_imm/status

/ghost/tracker_mh/target_odom
/ghost/tracker_mh/futures_json
/ghost/tracker_mh/status
```

Shared input:

```text
/ghost/vision/target_pose
```

## Deterministic closed-loop GNC SIL

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/closed_loop_gnc_sil.py \
  --out ghost_gnc_sil/manual
```

## Controlled covariance collection

On the Raspberry Pi with the USB webcam available:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

Do not begin the physical grid or formal motion campaign until the controlled-R quality gate is accepted and the same camera setup remains locked.

## Formal paired campaign

Initialize after dry runs and parameter lock:

```bash
python3 ghost_sim_ros2/tools/campaign_operations.py \
  --template ghost_sim_ros2/docs/IMM_MH_CAMPAIGN_MANIFEST.example.json \
  --out ~/ghost_trials/imm_mh_campaign_v1 \
  --resolve-protocol-commit \
  --repo-root .
```

Run one local cue sequence:

```bash
python3 ghost_sim_ros2/tools/trial_conductor.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --sequence 1
```

Actual measured vision gaps—not browser timing alone—determine acceptance.

## Analysis and integrity

Audited campaign analysis:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/campaign_analysis_runner.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --out-dir ~/ghost_trials/imm_mh_campaign_v1/analysis
```

Package evidence:

```bash
python3 ghost_sim_ros2/tools/evidence_integrity.py package \
  --source ~/ghost_trials/imm_mh_campaign_v1 \
  --archive ~/ghost_evidence/imm_mh_campaign_v1.zip \
  --profile campaign \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf
```

## Current boundary

All meaningful hardware-free preparation is complete. Physical covariance, grid truth, repeated paired trials, real USB/Pi performance, exact BOM/photos, and the final validated public metrics still require the actual hardware session.

The package does not currently claim:

- validated real-world tracking accuracy;
- formal IMM superiority on physical trials;
- production robustness;
- general object tracking beyond AprilTags;
- PX4/HIL integration;
- real vehicle command;
- flight readiness or flight testing.
