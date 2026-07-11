#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: collect_controlled_r_trial.sh [--check-ros-environment] [-h|--help]

Collect one controlled stationary AprilTag dataset for empirical R analysis.

Options:
  -h, --help                 Show this help and exit without creating evidence.
  --check-ros-environment    Source available ROS setup files safely, then exit.

Major environment variables:
  DEVICE, CALIB_PATH, TAG_SIZE_M, TRIAL_ROOT, TRIAL_DIR
  RECORD_DURATION_S, ANALYSIS_START_S, ANALYSIS_END_S
  MIN_ANALYSIS_RATE_HZ, MAX_ANALYSIS_GAP_S, AUTO_START_PUBLISHER
  EXPOSURE_AUTO, EXPOSURE_ABSOLUTE
  WHITE_BALANCE_TEMPERATURE_AUTO, WHITE_BALANCE_TEMPERATURE
  FOCUS_AUTO, FOCUS_ABSOLUTE
EOF
}

MODE=collect
case "${1:-}" in
  "") ;;
  -h|--help)
    usage
    exit 0
    ;;
  --check-ros-environment)
    MODE=check_ros_environment
    ;;
  *)
    printf 'ERROR: unknown argument: %s\n' "$1" >&2
    usage >&2
    exit 2
    ;;
esac
if (( $# > 1 )); then
  printf 'ERROR: unexpected positional arguments\n' >&2
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source_ros_setup() {
  local setup_file="$1"
  local nounset_was_set=0
  local source_status
  [[ -f "$setup_file" ]] || return 0

  case "$-" in
    *u*)
      nounset_was_set=1
      set +u
      ;;
  esac
  if source "$setup_file"; then
    source_status=0
  else
    source_status=$?
  fi
  if [[ "$nounset_was_set" -eq 1 ]]; then
    set -u
  fi
  return "$source_status"
}

if [[ "$MODE" == "check_ros_environment" ]]; then
  source_ros_setup /opt/ros/jazzy/setup.bash
  source_ros_setup "$HOME/ghost_ws/install/setup.bash"
  printf 'ROS environment setup completed with nounset restored.\n'
  exit 0
fi
REPO_ROOT="$(cd "$PACKAGE_ROOT/.." && pwd)"

DEVICE="${DEVICE:-/dev/video0}"
TAG_SIZE_M="${TAG_SIZE_M:-0.10}"
CALIB_PATH="${CALIB_PATH:-$HOME/ghost_camera_calibration.json}"
TRIAL_ROOT="${TRIAL_ROOT:-$HOME/ghost_trials}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%SZ)"
TRIAL_DIR="${TRIAL_DIR:-$TRIAL_ROOT/controlled_R_$TIMESTAMP}"
RECORDER_ROOT="$TRIAL_DIR/recorder"
PROTOCOL_REL="docs/CONTROLLED_R_COLLECTION_PROTOCOL.md"
PROTOCOL_COMMIT="$(git -C "$REPO_ROOT" log -n 1 --format=%H -- "$PROTOCOL_REL")"

RECORD_DURATION_S="${RECORD_DURATION_S:-90}"
ANALYSIS_START_S="${ANALYSIS_START_S:-15}"
ANALYSIS_END_S="${ANALYSIS_END_S:-75}"
MIN_ANALYSIS_RATE_HZ="${MIN_ANALYSIS_RATE_HZ:-10.0}"
MAX_ANALYSIS_GAP_S="${MAX_ANALYSIS_GAP_S:-0.25}"
AUTO_START_PUBLISHER="${AUTO_START_PUBLISHER:-1}"

EXPOSURE_AUTO="${EXPOSURE_AUTO:-1}"
EXPOSURE_ABSOLUTE="${EXPOSURE_ABSOLUTE:-157}"
WHITE_BALANCE_TEMPERATURE_AUTO="${WHITE_BALANCE_TEMPERATURE_AUTO:-0}"
WHITE_BALANCE_TEMPERATURE="${WHITE_BALANCE_TEMPERATURE:-4600}"
FOCUS_AUTO="${FOCUS_AUTO:-0}"
FOCUS_ABSOLUTE="${FOCUS_ABSOLUTE:-0}"

PUBLISHER_PID=""
CONTROL_FAILURE=0
COLLECTION_FAILURE=0

mkdir -p "$TRIAL_DIR" "$RECORDER_ROOT"
LOG_FILE="$TRIAL_DIR/camera_control_lock_log.txt"
READBACK_TSV="$TRIAL_DIR/camera_control_readbacks.tsv"
: > "$LOG_FILE"
printf 'stage\tcontrol\texpected\tactual\tstatus\n' > "$READBACK_TSV"

log() {
  printf '%s\n' "$*" | tee -a "$LOG_FILE"
}

cleanup() {
  if [[ -n "$PUBLISHER_PID" ]] && kill -0 "$PUBLISHER_PID" 2>/dev/null; then
    log "Stopping helper-started AprilTag publisher PID=$PUBLISHER_PID"
    kill -INT "$PUBLISHER_PID" 2>/dev/null || true
    wait "$PUBLISHER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

require_prerequisites() {
  local missing=0
  for command_name in git python3 v4l2-ctl ros2 timeout; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      printf 'ERROR: required command not found: %s\n' "$command_name" >&2
      missing=1
    fi
  done
  if [[ ! -e "$DEVICE" ]]; then
    printf 'ERROR: camera device does not exist: %s\n' "$DEVICE" >&2
    missing=1
  fi
  if [[ ! -f "$CALIB_PATH" ]]; then
    printf 'ERROR: calibrated camera file does not exist: %s\n' "$CALIB_PATH" >&2
    missing=1
  fi
  if [[ -z "$PROTOCOL_COMMIT" ]]; then
    printf 'ERROR: no committed protocol revision found for %s\n' "$PROTOCOL_REL" >&2
    missing=1
  fi
  if [[ "$missing" -ne 0 ]]; then
    exit 2
  fi
}

capture_controls() {
  local out="$1"
  {
    echo "# device: $DEVICE"
    echo "# captured_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    echo "## --info"
    v4l2-ctl -d "$DEVICE" --info || true
    echo
    echo "## --list-ctrls"
    v4l2-ctl -d "$DEVICE" --list-ctrls || true
    echo
    echo "## --all"
    v4l2-ctl -d "$DEVICE" --all || true
  } > "$out"
}

control_supported() {
  local name="$1"
  v4l2-ctl -d "$DEVICE" --list-ctrls 2>/dev/null |
    grep -Eq "^[[:space:]]*$name[[:space:]]"
}

read_control_value() {
  local name="$1"
  v4l2-ctl -d "$DEVICE" --get-ctrl="$name" 2>/dev/null |
    awk -F: 'NF >= 2 {gsub(/[[:space:]]/, "", $2); print $2; exit}'
}

set_control_if_supported() {
  local name="$1"
  local value="$2"
  if control_supported "$name"; then
    if v4l2-ctl -d "$DEVICE" --set-ctrl="${name}=${value}" >> "$LOG_FILE" 2>&1; then
      log "SET: $name=$value"
    else
      log "FAILED_SET: $name=$value"
      CONTROL_FAILURE=1
    fi
  else
    log "UNSUPPORTED: $name"
    printf 'set\t%s\t%s\tUNSUPPORTED\tUNSUPPORTED\n' "$name" "$value" >> "$READBACK_TSV"
  fi
}

verify_control_if_supported() {
  local stage="$1"
  local name="$2"
  local expected="$3"
  if control_supported "$name"; then
    local actual
    actual="$(read_control_value "$name" || true)"
    if [[ "$actual" == "$expected" ]]; then
      log "READBACK_OK[$stage]: $name=$actual"
      printf '%s\t%s\t%s\t%s\tOK\n' "$stage" "$name" "$expected" "$actual" >> "$READBACK_TSV"
    else
      log "READBACK_MISMATCH[$stage]: $name expected=$expected actual=${actual:-MISSING}"
      printf '%s\t%s\t%s\t%s\tMISMATCH\n' \
        "$stage" "$name" "$expected" "${actual:-MISSING}" >> "$READBACK_TSV"
      CONTROL_FAILURE=1
    fi
  else
    printf '%s\t%s\t%s\tUNSUPPORTED\tUNSUPPORTED\n' \
      "$stage" "$name" "$expected" >> "$READBACK_TSV"
  fi
}

verify_all_controls() {
  local stage="$1"
  verify_control_if_supported "$stage" exposure_auto "$EXPOSURE_AUTO"
  verify_control_if_supported "$stage" exposure_absolute "$EXPOSURE_ABSOLUTE"
  verify_control_if_supported "$stage" white_balance_temperature_auto "$WHITE_BALANCE_TEMPERATURE_AUTO"
  verify_control_if_supported "$stage" white_balance_temperature "$WHITE_BALANCE_TEMPERATURE"
  verify_control_if_supported "$stage" focus_auto "$FOCUS_AUTO"
  verify_control_if_supported "$stage" focus_absolute "$FOCUS_ABSOLUTE"
}

capture_one_vision_sample() {
  local out="$1"
  timeout 6s ros2 topic echo /ghost/vision/target_pose --once > "$out" 2>&1
}

wait_for_vision_sample() {
  local attempts="${1:-15}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if capture_one_vision_sample "$TRIAL_DIR/preflight_vision_sample.txt"; then
      log "VISION_PREFLIGHT_OK: received /ghost/vision/target_pose sample on attempt $i"
      return 0
    fi
    sleep 1
  done
  return 1
}

start_publisher_if_needed() {
  if capture_one_vision_sample "$TRIAL_DIR/preflight_vision_sample.txt"; then
    log "VISION_SOURCE: using already-running publisher"
    return 0
  fi

  if [[ "$AUTO_START_PUBLISHER" != "1" ]]; then
    log "VISION_PREFLIGHT_FAILED: no sample and AUTO_START_PUBLISHER=$AUTO_START_PUBLISHER"
    return 1
  fi
  if [[ ! -x "$HOME/ghost_venv/bin/python" ]]; then
    log "VISION_PREFLIGHT_FAILED: $HOME/ghost_venv/bin/python is unavailable"
    return 1
  fi

  log "VISION_SOURCE: starting AprilTag publisher for controlled-R collection"
  "$HOME/ghost_venv/bin/python" \
    "$PACKAGE_ROOT/ghost_sim_ros2/apriltag_ros_only.py" \
    --device "$DEVICE" \
    --tag-size "$TAG_SIZE_M" \
    --calib "$CALIB_PATH" \
    > "$TRIAL_DIR/apriltag_publisher.log" 2>&1 &
  PUBLISHER_PID=$!
  printf '%s\n' "$PUBLISHER_PID" > "$TRIAL_DIR/apriltag_publisher.pid"

  if ! wait_for_vision_sample 20; then
    log "VISION_PREFLIGHT_FAILED: helper-started publisher produced no sample"
    tail -n 80 "$TRIAL_DIR/apriltag_publisher.log" | tee -a "$LOG_FILE" || true
    return 1
  fi
}

link_recorder_artifacts() {
  local child="$1"
  local file
  for file in \
    metadata.json \
    vision_pose.jsonl \
    imm_futures.jsonl \
    mh_futures.jsonl \
    status.jsonl \
    events.jsonl \
    metrics.jsonl \
    summary.json \
    summary.md; do
    if [[ -e "$child/$file" ]]; then
      ln -sfn "$child/$file" "$TRIAL_DIR/$file"
    fi
  done
}

require_prerequisites

source_ros_setup /opt/ros/jazzy/setup.bash
source_ros_setup "$HOME/ghost_ws/install/setup.bash"

cat <<EOF
Controlled R stationary trial directory:
  $TRIAL_DIR

Physical setup before continuing:
  1. Mount the camera rigidly.
  2. Mount/tape the AprilTag rigidly.
  3. Keep the tag clearly visible and roughly fronto-parallel.
  4. Keep lighting constant.
  5. Do not hold or touch either item during recording.
EOF

read -r -p "Measured camera-to-tag standoff in meters: " STANDOFF_M
if ! python3 - "$STANDOFF_M" <<'PY'
import math
import sys
try:
    value = float(sys.argv[1])
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if math.isfinite(value) and value > 0.0 else 1)
PY
then
  printf 'ERROR: standoff must be a finite number greater than zero.\n' >&2
  exit 2
fi
read -r -p "Lighting/setup note (brief): " SETUP_NOTE
read -r -p "Press Enter only when camera and tag are rigid and untouched: " _

cat > "$TRIAL_DIR/protocol_metadata.txt" <<EOF
protocol_file=$PROTOCOL_REL
protocol_commit_hash=$PROTOCOL_COMMIT
repo_head=$(git -C "$REPO_ROOT" rev-parse HEAD)
created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
device=$DEVICE
tag_size_m=$TAG_SIZE_M
calibration_path=$CALIB_PATH
standoff_m=$STANDOFF_M
setup_note=$SETUP_NOTE
analysis_window_s=$ANALYSIS_START_S-$ANALYSIS_END_S
record_duration_s=$RECORD_DURATION_S
minimum_acceptable_analysis_rate_hz=$MIN_ANALYSIS_RATE_HZ
maximum_acceptable_analysis_gap_s=$MAX_ANALYSIS_GAP_S
publisher_covariance_note=POSE_COVARIANCE_METADATA_NOT_USED_TO_ESTIMATE_EMPIRICAL_R
accuracy_status=DOES_NOT_VALIDATE_TRACKER_ACCURACY
EOF

git -C "$REPO_ROOT" status --short --branch > "$TRIAL_DIR/git_status.txt"
capture_controls "$TRIAL_DIR/camera_controls_before.txt"

set_control_if_supported exposure_auto "$EXPOSURE_AUTO"
set_control_if_supported exposure_absolute "$EXPOSURE_ABSOLUTE"
set_control_if_supported white_balance_temperature_auto "$WHITE_BALANCE_TEMPERATURE_AUTO"
set_control_if_supported white_balance_temperature "$WHITE_BALANCE_TEMPERATURE"
set_control_if_supported focus_auto "$FOCUS_AUTO"
set_control_if_supported focus_absolute "$FOCUS_ABSOLUTE"

capture_controls "$TRIAL_DIR/camera_controls_after_set.txt"
verify_all_controls after_set
if [[ "$CONTROL_FAILURE" -ne 0 ]]; then
  log "ABORT: supported camera controls failed set/readback before collection"
  printf 'REJECT_CAMERA_CONTROL_LOCK\n' > "$TRIAL_DIR/final_collection_status.txt"
  exit 1
fi

if ! start_publisher_if_needed; then
  printf 'REJECT_NO_LIVE_VISION_SAMPLE\n' > "$TRIAL_DIR/final_collection_status.txt"
  exit 1
fi

capture_controls "$TRIAL_DIR/camera_controls_pre_record.txt"
verify_all_controls pre_record
if [[ "$CONTROL_FAILURE" -ne 0 ]]; then
  log "ABORT: supported camera controls changed after opening the camera"
  printf 'REJECT_CAMERA_CONTROL_CHANGED_ON_OPEN\n' > "$TRIAL_DIR/final_collection_status.txt"
  exit 1
fi

cat <<EOF

Preflight passed. The helper will now record exactly $RECORD_DURATION_S seconds.
Do not touch the table, camera, AprilTag, cable, or lighting.
Press Enter to start.
EOF
read -r

set +e
timeout --signal=INT --kill-after=5s "${RECORD_DURATION_S}s" \
  ros2 run ghost_sim_ros2 trial_recorder --ros-args \
  -p trial_root:="$RECORDER_ROOT" \
  > "$TRIAL_DIR/trial_recorder.log" 2>&1
RECORDER_STATUS=$?
set -e
log "RECORDER_EXIT_STATUS: $RECORDER_STATUS"

RECORDER_CHILD="$(
  find "$RECORDER_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
    sort -nr |
    head -n 1 |
    cut -d' ' -f2-
)"
if [[ -z "$RECORDER_CHILD" || ! -d "$RECORDER_CHILD" ]]; then
  log "REJECT: trial recorder did not create a child directory"
  printf 'REJECT_NO_RECORDER_CHILD\n' > "$TRIAL_DIR/final_collection_status.txt"
  exit 1
fi
printf '%s\n' "$RECORDER_CHILD" > "$TRIAL_DIR/recorder_child_dir.txt"
link_recorder_artifacts "$RECORDER_CHILD"

capture_controls "$TRIAL_DIR/camera_controls_after_trial.txt"
verify_all_controls after_trial

cat <<EOF

Physical integrity attestation:
Type exactly NO only if the camera, tag, table, cable, and lighting remained unchanged
and nobody touched the setup during the full recording.
EOF
read -r -p "Did any physical setup or lighting change occur? Type NO to attest: " PHYSICAL_CHANGE_ATTESTATION
printf 'physical_change_question=Did any physical setup or lighting change occur?\nresponse=%s\nrecorded_at_utc=%s\n' \
  "$PHYSICAL_CHANGE_ATTESTATION" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > "$TRIAL_DIR/operator_attestation.txt"
if [[ "$PHYSICAL_CHANGE_ATTESTATION" != "NO" ]]; then
  log "REJECT: operator did not attest that the physical setup remained unchanged"
  COLLECTION_FAILURE=1
fi
if [[ "$CONTROL_FAILURE" -ne 0 ]]; then
  log "REJECT: supported camera controls changed or could not be read after trial"
  COLLECTION_FAILURE=1
fi

if [[ ! -s "$TRIAL_DIR/vision_pose.jsonl" ]]; then
  log "REJECT: resolved vision_pose.jsonl is missing or empty"
  COLLECTION_FAILURE=1
else
  set +e
  python3 "$PACKAGE_ROOT/analysis/controlled_r_collection_quality.py" \
    "$TRIAL_DIR/vision_pose.jsonl" \
    --record-duration-s "$RECORD_DURATION_S" \
    --analysis-start-s "$ANALYSIS_START_S" \
    --analysis-end-s "$ANALYSIS_END_S" \
    --min-analysis-rate-hz "$MIN_ANALYSIS_RATE_HZ" \
    --max-analysis-gap-s "$MAX_ANALYSIS_GAP_S" \
    --json-out "$TRIAL_DIR/collection_quality.json" \
    --md-out "$TRIAL_DIR/collection_quality.md" \
    > "$TRIAL_DIR/collection_quality_console.txt" 2>&1
  QUALITY_STATUS=$?
  set -e
  if [[ "$QUALITY_STATUS" -ne 0 ]]; then
    log "REJECT: collection quality gate failed"
    COLLECTION_FAILURE=1
  fi
fi

if [[ "$COLLECTION_FAILURE" -eq 0 ]]; then
  python3 "$PACKAGE_ROOT/tools/export_vision_pose_csv.py" \
    "$TRIAL_DIR/vision_pose.jsonl" \
    --out "$TRIAL_DIR/vision_pose_log.csv"

  PYTHONPATH="$PACKAGE_ROOT" python3 "$PACKAGE_ROOT/analysis/controlled_r_protocol_analysis.py" \
    --csv "$TRIAL_DIR/vision_pose_log.csv" \
    --json-out "$TRIAL_DIR/noise_summary.json" \
    --md-out "$TRIAL_DIR/noise_summary.md" \
    | tee "$TRIAL_DIR/noise_summary_console.txt"

  printf 'ACCEPTABLE_FOR_ENGINEER_REVIEW_DOES_NOT_VALIDATE_TRACKER_ACCURACY\n' \
    > "$TRIAL_DIR/final_collection_status.txt"
  log "Controlled R collection and fixed-window analysis completed."
else
  printf 'REJECT_COLLECTION_PRESERVE_ALL_ARTIFACTS\n' \
    > "$TRIAL_DIR/final_collection_status.txt"
  log "Controlled R collection rejected. Artifacts were preserved for diagnosis."
fi

cat <<EOF

Trial directory:
  $TRIAL_DIR

Final status:
  $(cat "$TRIAL_DIR/final_collection_status.txt")

Review:
  $TRIAL_DIR/collection_quality.md
  $TRIAL_DIR/noise_summary.md
  $TRIAL_DIR/camera_control_readbacks.tsv
EOF

if [[ "$COLLECTION_FAILURE" -ne 0 ]]; then
  exit 1
fi
