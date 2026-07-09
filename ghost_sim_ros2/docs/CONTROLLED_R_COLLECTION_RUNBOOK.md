# Controlled R Collection Runbook

This runbook is for the later manual camera and AprilTag session. Do not run collection until the physical setup is ready.

## Manual Sequence

1. Checkout `main` containing the committed protocol, then use the review branch containing the helper scripts only after confirming the protocol commit exists in history:

   ```bash
   cd ~/ghost_ws/src/ghost-vins-eskf
   git log --oneline --decorate -8
   git log -n 1 --format=%H -- docs/CONTROLLED_R_COLLECTION_PROTOCOL.md
   ```

2. Confirm the protocol commit hash is recorded before collection. The protocol file is predeclared and must not be edited after data collection begins.

3. Start preview and verify the camera sees the AprilTag clearly.

4. Lock camera controls and keep readbacks:

   ```bash
   DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
   ```

   The helper records `camera_controls_before.txt`, `camera_controls_after_set.txt`, `camera_controls_after_trial.txt`, `protocol_metadata.txt`, and `git_status.txt` under a timestamped `~/ghost_trials/controlled_R_<timestamp>` directory. Unsupported camera controls must remain documented in `camera_control_lock_log.txt`.

5. Place the stationary tag rigidly. Measure and record standoff distance. Keep the camera, tag, table, and lighting fixed.

6. Run collection for exactly 90 seconds. The helper uses the known repo recorder command:

   ```bash
   cd ~/ghost_ws
   source /opt/ros/jazzy/setup.bash
   source install/setup.bash
   ros2 run ghost_sim_ros2 trial_recorder --ros-args -p trial_root:="$TRIAL_DIR"
   ```

7. Run stationary noise analysis on seconds 15-75 only:

   ```bash
   cd ~/ghost_ws/src/ghost-vins-eskf/ghost_sim_ros2
   python3 tools/export_vision_pose_csv.py \
     "$TRIAL_DIR/vision_pose.jsonl" \
     --out "$TRIAL_DIR/vision_pose_log.csv"

   awk -F, 'NR==1 || ($1 >= 15 && $1 <= 75)' \
     "$TRIAL_DIR/vision_pose_log.csv" \
     > "$TRIAL_DIR/vision_pose_log_15_75.csv"

   python3 tools/make_stationary_noise_summary.py \
     --csv "$TRIAL_DIR/vision_pose_log_15_75.csv" \
     --json-out "$TRIAL_DIR/noise_summary.json" \
     --md-out "$TRIAL_DIR/noise_summary.md" \
     --include-detrended-r
   ```

8. Save `noise_summary.md` and `noise_summary.json` in the trial directory with the raw log, camera readbacks, git status, and protocol metadata.

9. Only after those artifacts exist, use the raw seconds 15-75 covariance as a candidate controlled `R`. This estimates measurement noise only and does not validate tracker accuracy.
