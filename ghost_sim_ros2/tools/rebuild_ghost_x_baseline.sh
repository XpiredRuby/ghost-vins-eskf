#!/usr/bin/env bash
set -eo pipefail

REPO_ROOT="${REPO_ROOT:-$HOME/ghost_ws/src/ghost-vins-eskf}"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/ghost_ws}"
HARDWARE_BAG="${HARDWARE_BAG:-$HOME/ghost_ws/bags/live_camera_calibrated_R_01}"
SESSION_ROOT="${SESSION_ROOT:-$HOME/ghost_trials/physical_validation_20260711T183400Z}"
CALIBRATION="${CALIBRATION:-$HOME/ghost_camera_calibration.json}"
PLOT_OUT="${PLOT_OUT:-$REPO_ROOT/ghost_sim_ros2/docs/assets/ghost_live_plots}"

source /opt/ros/jazzy/setup.bash
if [[ -f "$WORKSPACE_ROOT/install/setup.bash" ]]; then
  source "$WORKSPACE_ROOT/install/setup.bash"
fi

cd "$REPO_ROOT"

python3 ghost_sim_ros2/tools/plot_live_bag.py \
  "$HARDWARE_BAG" \
  --out "$PLOT_OUT"

python3 ghost_sim_ros2/tools/ghost_x_baseline_manifest.py \
  --repo-root "$REPO_ROOT" \
  --session-root "$SESSION_ROOT" \
  --hardware-bag "$HARDWARE_BAG" \
  --calibration "$CALIBRATION" \
  --out ghost_sim_ros2/docs/GHOST_X_BASELINE_MANIFEST.json \
  --strict

PYTHONPATH=ghost_sim_ros2 \
python3 -m pytest -q \
  ghost_sim_ros2/test/test_ghost_world.py \
  ghost_sim_ros2/test/test_signed_mh_local_frame.py

printf '\nGHOST-X G0 baseline rebuild complete.\n'
printf 'Manifest: %s\n' "$REPO_ROOT/ghost_sim_ros2/docs/GHOST_X_BASELINE_MANIFEST.json"
printf 'Plots: %s\n' "$PLOT_OUT"
