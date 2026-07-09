#!/usr/bin/env bash
set -euo pipefail

DEVICE="${DEVICE:-/dev/video0}"
TRIAL_ROOT="${TRIAL_ROOT:-$HOME/ghost_trials}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%SZ)"
TRIAL_DIR="${TRIAL_DIR:-$TRIAL_ROOT/controlled_R_$TIMESTAMP}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
PROTOCOL_PATH="docs/CONTROLLED_R_COLLECTION_PROTOCOL.md"
PROTOCOL_COMMIT="$(git log -n 1 --format=%H -- "$PROTOCOL_PATH")"

EXPOSURE_AUTO="${EXPOSURE_AUTO:-1}"
EXPOSURE_ABSOLUTE="${EXPOSURE_ABSOLUTE:-157}"
WHITE_BALANCE_TEMPERATURE_AUTO="${WHITE_BALANCE_TEMPERATURE_AUTO:-0}"
WHITE_BALANCE_TEMPERATURE="${WHITE_BALANCE_TEMPERATURE:-4600}"
FOCUS_AUTO="${FOCUS_AUTO:-0}"
FOCUS_ABSOLUTE="${FOCUS_ABSOLUTE:-0}"

mkdir -p "$TRIAL_DIR"

log_file="$TRIAL_DIR/camera_control_lock_log.txt"
: > "$log_file"

log() {
  printf '%s\n' "$*" | tee -a "$log_file"
}

capture_controls() {
  local out="$1"
  {
    echo "# device: $DEVICE"
    echo "# captured_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if command -v v4l2-ctl >/dev/null 2>&1; then
      echo
      echo "## --list-ctrls"
      v4l2-ctl -d "$DEVICE" --list-ctrls || true
      echo
      echo "## --all"
      v4l2-ctl -d "$DEVICE" --all || true
    else
      echo "v4l2-ctl not found"
    fi
  } > "$out"
}

control_supported() {
  local name="$1"
  v4l2-ctl -d "$DEVICE" --list-ctrls 2>/dev/null | grep -Eq "^[[:space:]]*$name[[:space:]]"
}

set_control_if_supported() {
  local name="$1"
  local value="$2"
  if ! command -v v4l2-ctl >/dev/null 2>&1; then
    log "UNSUPPORTED: $name cannot be set because v4l2-ctl is not installed"
    return 0
  fi
  if control_supported "$name"; then
    if v4l2-ctl -d "$DEVICE" --set-ctrl="${name}=${value}" >> "$log_file" 2>&1; then
      log "SET: $name=$value"
    else
      log "FAILED_SET: $name=$value"
    fi
  else
    log "UNSUPPORTED: $name"
  fi
}

cat > "$TRIAL_DIR/protocol_metadata.txt" <<EOF
protocol_file=$PROTOCOL_PATH
protocol_commit_hash=$PROTOCOL_COMMIT
repo_head=$(git rev-parse HEAD)
created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
device=$DEVICE
analysis_window_s=15-75
record_duration_s=90
EOF

git status --short --branch > "$TRIAL_DIR/git_status.txt"

cat <<EOF
Controlled R stationary trial directory:
  $TRIAL_DIR

Manual setup before continuing:
  1. Mount the camera rigidly.
  2. Mount the AprilTag rigidly and fronto-parallel if practical.
  3. Measure and record standoff distance.
  4. Confirm preview and tag visibility.
  5. Keep lighting constant.
  6. Do not touch the setup during the 90 second recording.

Press Enter only after the physical setup is ready.
EOF
read -r

capture_controls "$TRIAL_DIR/camera_controls_before.txt"

set_control_if_supported exposure_auto "$EXPOSURE_AUTO"
set_control_if_supported exposure_absolute "$EXPOSURE_ABSOLUTE"
set_control_if_supported white_balance_temperature_auto "$WHITE_BALANCE_TEMPERATURE_AUTO"
set_control_if_supported white_balance_temperature "$WHITE_BALANCE_TEMPERATURE"
set_control_if_supported focus_auto "$FOCUS_AUTO"
set_control_if_supported focus_absolute "$FOCUS_ABSOLUTE"

capture_controls "$TRIAL_DIR/camera_controls_after_set.txt"

cat <<EOF

Start the AprilTag publisher and trackers in separate terminals if they are not already running.
Known repo commands:

  source ~/ghost_venv/bin/activate
  python $REPO_ROOT/ghost_sim_ros2/ghost_sim_ros2/apriltag_ros_only.py --device "$DEVICE" --tag-size 0.10 --use-controlled-r-candidate

  cd ~/ghost_ws
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
  ros2 run ghost_sim_ros2 formal_imm_tracker
  ros2 run ghost_sim_ros2 mh_tracker

This helper will run the known trial recorder for exactly 90 seconds.
Do not touch the table, camera, or tag during recording.

Press Enter to start the 90 second recorder.
EOF
read -r

cd "$HOME/ghost_ws"
if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  # shellcheck disable=SC1091
  source /opt/ros/jazzy/setup.bash
fi
if [[ -f install/setup.bash ]]; then
  # shellcheck disable=SC1091
  source install/setup.bash
fi
set +e
timeout 90s ros2 run ghost_sim_ros2 trial_recorder --ros-args -p trial_root:="$TRIAL_DIR"
recorder_status=$?
set -e

if [[ "$recorder_status" -ne 0 && "$recorder_status" -ne 124 ]]; then
  log "RECORDER_EXIT_STATUS: $recorder_status"
else
  log "RECORDER_EXIT_STATUS: $recorder_status (expected 124 if timeout stopped the 90 second trial)"
fi

capture_controls "$TRIAL_DIR/camera_controls_after_trial.txt"

cat <<EOF

Controlled R collection finished.
Trial directory:
  $TRIAL_DIR

Next manual analysis step:
  cd $REPO_ROOT/ghost_sim_ros2
  python3 tools/export_vision_pose_csv.py "\$TRIAL_DIR/vision_pose.jsonl" --out "\$TRIAL_DIR/vision_pose_log.csv"
  awk -F, 'NR==1 || (\$1 >= 15 && \$1 <= 75)' "\$TRIAL_DIR/vision_pose_log.csv" > "\$TRIAL_DIR/vision_pose_log_15_75.csv"
  python3 tools/make_stationary_noise_summary.py --csv "\$TRIAL_DIR/vision_pose_log_15_75.csv" --json-out "\$TRIAL_DIR/noise_summary.json" --md-out "\$TRIAL_DIR/noise_summary.md" --include-detrended-r

If the recorder wrote a timestamped child directory, copy or symlink its JSONL logs into the trial root before analysis.
EOF
