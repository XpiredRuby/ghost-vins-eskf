#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: collect_controlled_r_direct_trial.sh [-h|--help]

Collect a controlled stationary AprilTag covariance trial directly from the
camera/detector/solvePnP path, bypassing ROS DDS transport.

Environment variables:
  DEVICE, TAG_SIZE_M, CALIB_PATH, TRIAL_ROOT, TRIAL_DIR
  RECORD_DURATION_S, ANALYSIS_START_S, ANALYSIS_END_S
  MIN_ANALYSIS_RATE_HZ, MAX_ANALYSIS_GAP_S
  DIRECT_CAPTURE_PYTHON, SETUP_NOTE, STANDOFF_M
  ATTESTATION_SOURCE, POSTRUN_HUMAN_ATTESTATION
  AUTO_EXPOSURE, EXPOSURE_TIME_ABSOLUTE, EXPOSURE_DYNAMIC_FRAMERATE
  WHITE_BALANCE_AUTOMATIC, WHITE_BALANCE_TEMPERATURE, POWER_LINE_FREQUENCY
EOF
}

case "${1:-}" in
  "") ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    printf 'ERROR: unknown argument: %s\n' "$1" >&2
    usage >&2
    exit 2
    ;;
esac
if (( $# > 1 )); then
  printf 'ERROR: unexpected positional arguments\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PACKAGE_ROOT/.." && pwd)"

DEVICE="${DEVICE:-/dev/video0}"
TAG_SIZE_M="${TAG_SIZE_M:-0.10}"
CALIB_PATH="${CALIB_PATH:-$HOME/ghost_camera_calibration.json}"
TRIAL_ROOT="${TRIAL_ROOT:-$HOME/ghost_trials}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%SZ)"
TRIAL_DIR="${TRIAL_DIR:-$TRIAL_ROOT/controlled_R_direct_$TIMESTAMP}"
RECORD_DURATION_S="${RECORD_DURATION_S:-90}"
ANALYSIS_START_S="${ANALYSIS_START_S:-15}"
ANALYSIS_END_S="${ANALYSIS_END_S:-75}"
MIN_ANALYSIS_RATE_HZ="${MIN_ANALYSIS_RATE_HZ:-10.0}"
MAX_ANALYSIS_GAP_S="${MAX_ANALYSIS_GAP_S:-0.25}"
DIRECT_CAPTURE_PYTHON="${DIRECT_CAPTURE_PYTHON:-$HOME/ghost_venv/bin/python}"
SETUP_NOTE="${SETUP_NOTE:-DIRECT_SOURCE_CONTROLLED_R_COLLECTION}"
STANDOFF_M="${STANDOFF_M:-NOT_RULER_MEASURED_NOT_USED_IN_COVARIANCE_ANALYSIS}"
ATTESTATION_SOURCE="${ATTESTATION_SOURCE:-NOT_PROVIDED}"
POSTRUN_HUMAN_ATTESTATION="${POSTRUN_HUMAN_ATTESTATION:-NOT_COLLECTED}"

AUTO_EXPOSURE="${AUTO_EXPOSURE:-1}"
EXPOSURE_TIME_ABSOLUTE="${EXPOSURE_TIME_ABSOLUTE:-157}"
EXPOSURE_DYNAMIC_FRAMERATE="${EXPOSURE_DYNAMIC_FRAMERATE:-0}"
WHITE_BALANCE_AUTOMATIC="${WHITE_BALANCE_AUTOMATIC:-0}"
WHITE_BALANCE_TEMPERATURE="${WHITE_BALANCE_TEMPERATURE:-4600}"
POWER_LINE_FREQUENCY="${POWER_LINE_FREQUENCY:-2}"

mkdir -p "$TRIAL_DIR"
READBACK_TSV="$TRIAL_DIR/camera_control_readbacks.tsv"
printf 'stage\tcontrol\texpected\tactual\tstatus\n' > "$READBACK_TSV"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$1" >&2
    exit 2
  }
}

for cmd in git v4l2-ctl /usr/bin/python3; do
  require_command "$cmd"
done
[[ -x "$DIRECT_CAPTURE_PYTHON" ]] || {
  printf 'ERROR: direct capture Python is unavailable: %s\n' "$DIRECT_CAPTURE_PYTHON" >&2
  exit 2
}
[[ -e "$DEVICE" ]] || {
  printf 'ERROR: camera device does not exist: %s\n' "$DEVICE" >&2
  exit 2
}
[[ -f "$CALIB_PATH" ]] || {
  printf 'ERROR: calibration file does not exist: %s\n' "$CALIB_PATH" >&2
  exit 2
}

capture_controls() {
  local out="$1"
  {
    echo "# device: $DEVICE"
    echo "# captured_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    v4l2-ctl -d "$DEVICE" --all
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
    awk -F: 'NF >= 2 {
      value=$2
      sub(/^[[:space:]]+/, "", value)
      split(value, parts, /[[:space:]]+/)
      print parts[1]
      exit
    }'
}

set_and_verify() {
  local name="$1"
  local expected="$2"
  if ! control_supported "$name"; then
    printf 'set\t%s\t%s\tUNSUPPORTED\tUNSUPPORTED\n' "$name" "$expected" >> "$READBACK_TSV"
    return 0
  fi
  v4l2-ctl -d "$DEVICE" --set-ctrl="${name}=${expected}" >/dev/null
  local actual
  actual="$(read_control_value "$name")"
  if [[ "$actual" != "$expected" ]]; then
    printf 'set\t%s\t%s\t%s\tMISMATCH\n' "$name" "$expected" "$actual" >> "$READBACK_TSV"
    printf 'ERROR: control readback mismatch: %s expected=%s actual=%s\n' "$name" "$expected" "$actual" >&2
    exit 1
  fi
  printf 'set\t%s\t%s\t%s\tOK\n' "$name" "$expected" "$actual" >> "$READBACK_TSV"
}

capture_controls "$TRIAL_DIR/camera_controls_before.txt"
set_and_verify auto_exposure "$AUTO_EXPOSURE"
set_and_verify exposure_time_absolute "$EXPOSURE_TIME_ABSOLUTE"
set_and_verify exposure_dynamic_framerate "$EXPOSURE_DYNAMIC_FRAMERATE"
set_and_verify white_balance_automatic "$WHITE_BALANCE_AUTOMATIC"
set_and_verify white_balance_temperature "$WHITE_BALANCE_TEMPERATURE"
set_and_verify power_line_frequency "$POWER_LINE_FREQUENCY"
capture_controls "$TRIAL_DIR/camera_controls_after_set.txt"

git -C "$REPO_ROOT" status --short --branch > "$TRIAL_DIR/git_status.txt"
cat > "$TRIAL_DIR/protocol_metadata.txt" <<EOF
created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
repo_head=$(git -C "$REPO_ROOT" rev-parse HEAD)
source=DIRECT_CAMERA_APRILTAG_SOLVEPNP_NO_ROS_TRANSPORT
device=$DEVICE
tag_size_m=$TAG_SIZE_M
calibration_path=$CALIB_PATH
standoff_m=$STANDOFF_M
setup_note=$SETUP_NOTE
record_duration_s=$RECORD_DURATION_S
analysis_window_s=$ANALYSIS_START_S-$ANALYSIS_END_S
minimum_acceptable_analysis_rate_hz=$MIN_ANALYSIS_RATE_HZ
maximum_acceptable_analysis_gap_s=$MAX_ANALYSIS_GAP_S
coordinate_mapping=position.x=cam_z_position.y=cam_x
transport_note=ROS_DDS_BYPASSED_TO_MEASURE_SENSOR_PIPELINE_WITHOUT_MIDDLEWARE_RECEIPT_GAPS
accuracy_status=DOES_NOT_VALIDATE_TRACKER_ACCURACY
EOF
cat > "$TRIAL_DIR/operator_attestation.txt" <<EOF
attestation_source=$ATTESTATION_SOURCE
postrun_human_attestation=$POSTRUN_HUMAN_ATTESTATION
automated_checks=pose_continuity_pose_span_tag_identity_brightness_camera_control_readback
EOF

"$DIRECT_CAPTURE_PYTHON" "$SCRIPT_DIR/direct_controlled_r_capture.py" \
  --device "$DEVICE" \
  --duration-s "$RECORD_DURATION_S" \
  --tag-size "$TAG_SIZE_M" \
  --calib "$CALIB_PATH" \
  --out-dir "$TRIAL_DIR" \
  > "$TRIAL_DIR/direct_capture_console.txt" 2>&1

capture_controls "$TRIAL_DIR/camera_controls_after_trial.txt"

/usr/bin/python3 "$PACKAGE_ROOT/analysis/controlled_r_collection_quality.py" \
  "$TRIAL_DIR/vision_pose.jsonl" \
  --record-duration-s "$RECORD_DURATION_S" \
  --analysis-start-s "$ANALYSIS_START_S" \
  --analysis-end-s "$ANALYSIS_END_S" \
  --min-analysis-rate-hz "$MIN_ANALYSIS_RATE_HZ" \
  --max-analysis-gap-s "$MAX_ANALYSIS_GAP_S" \
  --json-out "$TRIAL_DIR/collection_quality.json" \
  --md-out "$TRIAL_DIR/collection_quality.md" \
  > "$TRIAL_DIR/collection_quality_console.txt" 2>&1

/usr/bin/python3 "$PACKAGE_ROOT/tools/export_vision_pose_csv.py" \
  "$TRIAL_DIR/vision_pose.jsonl" \
  --out "$TRIAL_DIR/vision_pose_log.csv" \
  > "$TRIAL_DIR/export_console.txt" 2>&1

PYTHONPATH="$PACKAGE_ROOT" /usr/bin/python3 "$PACKAGE_ROOT/analysis/controlled_r_protocol_analysis.py" \
  --csv "$TRIAL_DIR/vision_pose_log.csv" \
  --json-out "$TRIAL_DIR/noise_summary.json" \
  --md-out "$TRIAL_DIR/noise_summary.md" \
  > "$TRIAL_DIR/noise_summary_console.txt" 2>&1

printf '%s\n' \
  'ACCEPTABLE_FOR_ENGINEERING_REVIEW_DIRECT_SOURCE_DOES_NOT_VALIDATE_TRACKER_ACCURACY' \
  > "$TRIAL_DIR/final_collection_status.txt"

printf 'Trial directory: %s\n' "$TRIAL_DIR"
printf 'Final status: %s\n' "$(cat "$TRIAL_DIR/final_collection_status.txt")"
