# GHOST Pi Validation Runbook: V1 Stationary Hide/Reveal and Exit Criterion 18.2

This runbook starts only after the software-regime PRs are merged:

```text
PR #18: offline stationary-hold software-regime scaffold
PR #19: live ROS tracker stationary-hold integration
```

This is the first controlled Pi-side validation step. It is not a dashboard demo and not a free-form hardware session.

## Goal

Close the assumed-state gap that previously caused bad logs:

```text
Do not assume camera settings are locked.
Set them, query them back, and store the confirmed readback in trial metadata before logging tracking data.
```

Then run a controlled stationary hide/reveal trial, export the raw vision samples to the canonical `t,x,y,z` CSV schema, and create the final `noise_summary.json` / `noise_summary.md` artifacts for controlled R review. This tooling prepares report-grade R characterization, but it does not by itself prove estimator accuracy.

## Required outputs

Each trial folder must contain:

```text
metadata.json
camera_controls_before.txt
camera_controls_after_set.txt
camera_controls_after_trial.txt
camera_lock_status.json
vision_pose_log.csv
tracker_futures.jsonl
tracker_status.txt
noise_summary.json
noise_summary.md
```

Do not accept a trial without the camera-control readbacks.

## Step 1 — Create trial folder and lock camera controls

From the `ghost_sim_ros2` package directory on the Pi:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf/ghost_sim_ros2
TRIAL_DIR=~/ghost_trials/18_2_stationary_hide_reveal_$(date +%Y%m%d_%H%M%S)
mkdir -p "$TRIAL_DIR"
bash tools/lock_uvc_camera_controls.sh /dev/video0 "$TRIAL_DIR"
cd "$TRIAL_DIR"
```

The helper writes:

```text
camera_controls_before.txt
camera_controls_after_set.txt
camera_lock_status.json
```

It applies the verified fixed/manual controls:

```text
auto_exposure=1
exposure_time_absolute=157
exposure_dynamic_framerate=0
gain=0
white_balance_automatic=0
white_balance_temperature=4600
power_line_frequency=2
```

The helper exits nonzero if readback does not match the requested fixed/manual values. The trial is invalid if readback still shows dynamic behavior enabled, such as:

```text
AGC / auto exposure still enabled
AWB still enabled
dynamic framerate still enabled
exposure/gain controls unavailable or unchanged from requested state
```

If the lock did not actually take, stop and fix camera control first. Do not record a 60 s tracker log and try to explain it afterward.

## Step 2 — Trial metadata

Create `metadata.json` before the tracking trial:

```json
{
  "trial_id": "18_2_stationary_hide_reveal_manual_exposure",
  "purpose": "Validate stationary hide/reveal behavior and rerun noise characterization with verified camera settings.",
  "software_state": {
    "pr_18": "merged",
    "pr_19": "merged",
    "stationary_threshold_status": "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R",
    "stationary_hold_prior_status": "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"
  },
  "camera_controls_verified_by_readback": true,
  "target_condition": "stationary before hide, hidden, then revealed at same location",
  "required_outputs": [
    "camera_controls_before.txt",
    "camera_controls_after_set.txt",
    "camera_controls_after_trial.txt",
    "camera_lock_status.json",
    "vision_pose_log.csv",
    "tracker_futures.jsonl",
    "tracker_status.txt",
    "noise_summary.json",
    "noise_summary.md"
  ]
}
```

## Step 3 — Stationary hide/reveal trial

Hold the AprilTag stationary long enough for the stationary gate window to fill:

```text
0-8 s: visible and stationary
8-16 s: hidden without moving the target
16-24 s: reveal at the same location
```

Acceptance behavior during hide:

```text
/ghost/tracker_mh/status contains: HIDDEN - STATIONARY HOLD
/ghost/tracker_mh/futures_json contains hidden_stationary_hold_active: true
rank-1 hypothesis model: stationary_hold
rank-1 vx_mps = 0.0
rank-1 vy_mps = 0.0
stationary_threshold_status: CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
stationary_hold_prior_status: CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
```

After `stationary_hold_max_s`, the tracker must stop indefinite hold behavior and fall back to the normal hypothesis/unknown behavior.

## Step 4 — Record live tracker evidence

Use the trial recorder so the vision stream is preserved as raw JSONL. Start it before the hide/reveal sequence and stop it immediately after the sequence:

```bash
cd ~/ghost_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run ghost_sim_ros2 trial_recorder --ros-args -p trial_root:="$TRIAL_DIR"
```

The recorder creates a timestamped subfolder under `$TRIAL_DIR` containing `vision_pose.jsonl`, `futures.jsonl`, `status.jsonl`, and summary artifacts. Keep those raw logs. If you also use `ros2 bag record`, keep the bag directory as the raw source of record.

For reviewer packet compatibility, copy or symlink the raw tracker logs into the trial root after recording:

```bash
REC_DIR=$(find "$TRIAL_DIR" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)
cp "$REC_DIR/futures.jsonl" "$TRIAL_DIR/tracker_futures.jsonl"
cp "$REC_DIR/status.jsonl" "$TRIAL_DIR/tracker_status.jsonl"
cp "$REC_DIR/vision_pose.jsonl" "$TRIAL_DIR/vision_pose.jsonl"
```

## Step 5 — Export canonical vision pose CSV

From the `ghost_sim_ros2` package directory, export raw samples without detrending or filtering:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf/ghost_sim_ros2
python3 tools/export_vision_pose_csv.py \
  "$TRIAL_DIR/vision_pose.jsonl" \
  --out "$TRIAL_DIR/vision_pose_log.csv"
```

If the raw source is a ROS 2 bag directory instead of trial-recorder JSONL:

```bash
python3 tools/export_vision_pose_csv.py \
  "$TRIAL_DIR/<bag_directory>" \
  --out "$TRIAL_DIR/vision_pose_log.csv" \
  --topic /ghost/vision/target_pose
```

The output CSV schema must be exactly:

```text
t,x,y,z
```

## Step 6 — Create final stationary noise summaries

Run the stationary noise report and empirical raw R generator:

```bash
python3 tools/make_stationary_noise_summary.py \
  --csv "$TRIAL_DIR/vision_pose_log.csv" \
  --json-out "$TRIAL_DIR/noise_summary.json" \
  --md-out "$TRIAL_DIR/noise_summary.md" \
  --include-detrended-r
```

The recommended empirical raw `R_xy` section is the candidate measurement covariance artifact for engineer review. The detrended R is diagnostic-only. Raw R may include colored/drift components and is not proof of white noise or estimator accuracy.


## Controlled-R candidate live parameters

After producing the controlled stable-window R candidate, use the same `R_xy` consistently in the AprilTag publisher and both live trackers for the next trial. This is a controlled-R candidate for integration testing; it does not validate estimator accuracy.

AprilTag publisher:

```bash
source ~/ghost_venv/bin/activate
python ~/ghost_ws/src/ghost-vins-eskf/ghost_sim_ros2/ghost_sim_ros2/apriltag_ros_only.py --device /dev/video0 --tag-size 0.10 --use-controlled-r-candidate
```

Formal IMM tracker parameters:

```bash
ros2 run ghost_sim_ros2 formal_imm_tracker --ros-args \
  -p measurement_r_xx_m2:=2.17492633008e-06 \
  -p measurement_r_xy_m2:=6.31889067707e-07 \
  -p measurement_r_yy_m2:=1.98048863448e-07
```

MH tracker parameters:

```bash
ros2 run ghost_sim_ros2 mh_tracker --ros-args \
  -p measurement_r_xx_m2:=2.17492633008e-06 \
  -p measurement_r_xy_m2:=6.31889067707e-07 \
  -p measurement_r_yy_m2:=1.98048863448e-07
```

The candidate matrix is:

```text
R_xy = [[2.17492633008e-06, 6.31889067707e-07],
        [6.31889067707e-07, 1.98048863448e-07]]
```

Live futures JSON should report `measurement_r_source=CONTROLLED_R_CANDIDATE_STABLE_60S_PENDING_ENGINEER_REVIEW` and `measurement_r_status=DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY`.

## Step 7 — Query camera readback again after trial

Immediately after the run:

```bash
v4l2-ctl -d /dev/video0 --list-ctrls > "$TRIAL_DIR/camera_controls_after_trial.txt"
```

Compare `camera_controls_after_set.txt` and `camera_controls_after_trial.txt`.

If exposure/gain/white-balance/framerate changed during the run, the trial cannot be used for final 18.2 evidence.

## Step 8 — Review noise characterization

Compare the new confirmed-control noise result against the uncontrolled baseline.

Minimum fields to report:

```text
std_x_m
std_y_m
lag1_autocorr_x
lag1_autocorr_y
PSD power fractions by band
dominant PSD peaks
Allan deviation slopes
stationary gate window speed distribution
stationary_hold_active fraction while visible-stationary
hidden_stationary_hold_active fraction while hidden
```

Baseline values to compare against:

```text
sigma_x: 0.0355 -> new value
lag-1 rho_x: 0.995 -> new value
~0.114 Hz harmonic peaks: persist or collapse?
```

The important question is:

```text
Was the earlier colored low-frequency drift mostly camera-control artifact, or is it fundamental to this sensor/pose pipeline?
```

## Step 9 — Pass/fail interpretation

A good run should show:

```text
1. Camera controls confirmed locked before and after the trial.
2. Stationary visible window enters stationary_hold before hide.
3. Hidden window publishes HIDDEN - STATIONARY HOLD.
4. futures_json rank-1 hypothesis is stationary_hold with zero velocity.
5. Candidate caveat fields are present in live futures_json.
6. `vision_pose_log.csv`, `noise_summary.json`, and `noise_summary.md` were generated from preserved raw samples.
7. Noise statistics are lower or at least now interpretable under confirmed camera settings.
8. If noise remains colored, thresholds stay candidate until covariance R is reviewed with the raw autocorrelation/PSD/Allan diagnostics.
```

A failed run includes any of:

```text
camera controls did not lock by readback
camera controls changed during trial
gate never entered stationary during visible stationary segment
hidden target showed dominant moving future despite stationary pre-hide evidence
futures_json missing threshold/prior caveat fields
post-trial analysis omits autocorrelation/PSD/Allan comparison or empirical raw R_xy
```

## Engineer review packet

Bring back these exact items for review:

```text
1. metadata.json
2. camera_controls_before.txt
3. camera_controls_after_set.txt
4. camera_controls_after_trial.txt
5. tracker_futures.jsonl for the hide/reveal window
6. tracker_status.txt for the hide/reveal window
7. vision pose log
8. noise_summary.md
9. noise_summary.json
10. camera_lock_status.json
11. a short note answering whether the 0.114 Hz peak persisted
```
