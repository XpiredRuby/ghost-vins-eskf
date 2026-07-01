#!/usr/bin/env bash
set -euo pipefail

SESSION="ghost"
CAMERA_DEVICE="${GHOST_CAMERA_DEVICE:-/dev/video0}"
TAG_SIZE="${GHOST_TAG_SIZE:-0.10}"
VIEW_URL="http://192.168.1.142:8081"

if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux is not installed. Run: sudo apt update && sudo apt install -y tmux"
  exit 1
fi

# Restart cleanly.
tmux kill-session -t "$SESSION" 2>/dev/null || true

tmux new-session -d -s "$SESSION" -n camera

tmux send-keys -t "$SESSION:camera" \
  "source /opt/ros/jazzy/setup.bash; source ~/ghost_venv/bin/activate; echo 'Camera viewer: ${VIEW_URL}'; python ~/ghost_live_apriltag_pose_calibrated.py --device ${CAMERA_DEVICE} --tag-size ${TAG_SIZE}" C-m

tmux new-window -t "$SESSION" -n mh_tracker

tmux send-keys -t "$SESSION:mh_tracker" \
  "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; ros2 run ghost_sim_ros2 mh_tracker" C-m

tmux new-window -t "$SESSION" -n status

tmux send-keys -t "$SESSION:status" \
  "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; while true; do clear; echo 'GHOST LIVE STATUS'; date; echo; echo 'TOPICS'; ros2 topic list | grep ghost || true; echo; echo 'MH STATUS'; timeout 0.5s ros2 topic echo /ghost/tracker_mh/status --once 2>/dev/null || true; echo; echo 'TOP FUTURES JSON'; timeout 0.5s ros2 topic echo /ghost/tracker_mh/futures_json --once 2>/dev/null | head -80 || true; sleep 0.5; done" C-m

tmux select-window -t "$SESSION:status"
echo "GHOST started. Controls: Ctrl+b then n/p to switch tabs, Ctrl+b then d to detach."
echo "Stop all: tmux kill-session -t ${SESSION}"
echo "Camera viewer: ${VIEW_URL}"
tmux attach -t "$SESSION"
