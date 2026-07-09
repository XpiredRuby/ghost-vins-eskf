#!/usr/bin/env bash
set -u

if [[ $# -ne 2 ]]; then
  echo "usage: bash tools/lock_uvc_camera_controls.sh /dev/video0 OUTDIR" >&2
  exit 2
fi

DEV="$1"
OUTDIR="$2"
mkdir -p "$OUTDIR"

BEFORE="$OUTDIR/camera_controls_before.txt"
AFTER="$OUTDIR/camera_controls_after_set.txt"
STATUS_JSON="$OUTDIR/camera_lock_status.json"

controls=(
  "auto_exposure=1"
  "exposure_time_absolute=157"
  "exposure_dynamic_framerate=0"
  "gain=0"
  "white_balance_automatic=0"
  "white_balance_temperature=4600"
  "power_line_frequency=2"
)

write_status() {
  local ok="$1"
  local message="$2"
  cat > "$STATUS_JSON" <<EOF
{
  "device": "$DEV",
  "status": "$ok",
  "message": "$message",
  "requested_settings": {
    "auto_exposure": 1,
    "exposure_time_absolute": 157,
    "exposure_dynamic_framerate": 0,
    "gain": 0,
    "white_balance_automatic": 0,
    "white_balance_temperature": 4600,
    "power_line_frequency": 2
  },
  "camera_controls_before": "camera_controls_before.txt",
  "camera_controls_after_set": "camera_controls_after_set.txt"
}
EOF
}

if ! command -v v4l2-ctl >/dev/null 2>&1; then
  write_status "FAIL" "v4l2-ctl not found"
  echo "v4l2-ctl not found" >&2
  exit 1
fi

if ! v4l2-ctl -d "$DEV" --list-ctrls > "$BEFORE"; then
  write_status "FAIL" "failed to read camera controls before setting"
  exit 1
fi

for setting in "${controls[@]}"; do
  if ! v4l2-ctl -d "$DEV" -c "$setting"; then
    write_status "FAIL" "failed to apply $setting"
    exit 1
  fi
done

if ! v4l2-ctl -d "$DEV" --list-ctrls > "$AFTER"; then
  write_status "FAIL" "failed to read camera controls after setting"
  exit 1
fi

check_value() {
  local name="$1"
  local expected="$2"
  local line
  line="$(grep -E "(^|[[:space:]])${name}([[:space:]]|$)" "$AFTER" || true)"
  if [[ -z "$line" ]]; then
    echo "missing readback for $name" >&2
    return 1
  fi
  if [[ "$line" != *"value=${expected}"* ]]; then
    echo "readback mismatch for $name: expected value=${expected}; got: $line" >&2
    return 1
  fi
}

failures=0
check_value "auto_exposure" "1" || failures=$((failures + 1))
check_value "exposure_time_absolute" "157" || failures=$((failures + 1))
check_value "exposure_dynamic_framerate" "0" || failures=$((failures + 1))
check_value "gain" "0" || failures=$((failures + 1))
check_value "white_balance_automatic" "0" || failures=$((failures + 1))
check_value "white_balance_temperature" "4600" || failures=$((failures + 1))
check_value "power_line_frequency" "2" || failures=$((failures + 1))

if [[ "$failures" -ne 0 ]]; then
  write_status "FAIL" "one or more camera-control readbacks did not match requested fixed/manual values"
  exit 1
fi

write_status "PASS" "camera controls matched requested fixed/manual readbacks"
echo "camera control lock readback PASS: $OUTDIR"
