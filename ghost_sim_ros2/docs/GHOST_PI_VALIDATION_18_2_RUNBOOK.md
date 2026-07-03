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

Then run a controlled stationary hide/reveal trial and compare the new manual-exposure noise result against the earlier uncontrolled stationary log.

## Required outputs

Each trial folder must contain:

```text
metadata.json
camera_controls_before.txt
camera_controls_after_set.txt
camera_controls_after_trial.txt
vision_pose_log.csv
tracker_futures.jsonl
tracker_status.txt
noise_summary.json
noise_summary.md
```

Do not accept a trial without the camera-control readbacks.

## Step 1 — Confirm camera control state

Before logging any target data, capture the actual returned controls:

```bash
mkdir -p ~/ghost_trials/18_2_stationary_hide_reveal_$(date +%Y%m%d_%H%M%S)
cd ~/ghost_trials/18_2_stationary_hide_reveal_*

v4l2-ctl -d /dev/video0 --list-ctrls > camera_controls_before.txt
```

Then set the intended fixed controls using the appropriate camera stack command for the current driver.

After setting, query again:

```bash
v4l2-ctl -d /dev/video0 --list-ctrls > camera_controls_after_set.txt
```

The trial is invalid if readback still shows dynamic behavior enabled, such as:

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

## Step 4 — Capture live tracker evidence

Capture the live futures payload during the whole trial:

```bash
ros2 topic echo /ghost/tracker_mh/futures_json > tracker_futures.jsonl
```

Capture status separately:

```bash
ros2 topic echo /ghost/tracker_mh/status > tracker_status.txt
```

Capture the raw vision pose stream used by the tracker:

```bash
ros2 topic echo /ghost/vision/target_pose > vision_pose_log.csv
```

If the exact logging format is not CSV, store the raw ROS output and convert it later. Do not discard raw logs.

## Step 5 — Query camera readback again after trial

Immediately after the run:

```bash
v4l2-ctl -d /dev/video0 --list-ctrls > camera_controls_after_trial.txt
```

Compare `camera_controls_after_set.txt` and `camera_controls_after_trial.txt`.

If exposure/gain/white-balance/framerate changed during the run, the trial cannot be used for final 18.2 evidence.

## Step 6 — Rerun noise characterization

Run the same stationary noise analysis used earlier, then compare against the uncontrolled baseline.

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

## Step 7 — Pass/fail interpretation

A good run should show:

```text
1. Camera controls confirmed locked before and after the trial.
2. Stationary visible window enters stationary_hold before hide.
3. Hidden window publishes HIDDEN - STATIONARY HOLD.
4. futures_json rank-1 hypothesis is stationary_hold with zero velocity.
5. Candidate caveat fields are present in live futures_json.
6. Noise statistics are lower or at least now interpretable under confirmed camera settings.
7. If noise remains colored, thresholds stay candidate until calibrated against that measured R.
```

A failed run includes any of:

```text
camera controls did not lock by readback
camera controls changed during trial
gate never entered stationary during visible stationary segment
hidden target showed dominant moving future despite stationary pre-hide evidence
futures_json missing threshold/prior caveat fields
post-trial analysis omits autocorrelation/PSD/Allan comparison
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
10. a short note answering whether the 0.114 Hz peak persisted
```
