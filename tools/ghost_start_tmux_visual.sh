#!/usr/bin/env bash
set -euo pipefail

SESSION="ghost"
CAMERA_DEVICE="${GHOST_CAMERA_DEVICE:-/dev/video0}"
TAG_SIZE="${GHOST_TAG_SIZE:-0.10}"
CAMERA_URL="http://192.168.1.142:8081"
DASHBOARD_URL="http://192.168.1.142:8090"

if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux is not installed. Run: sudo apt update && sudo apt install -y tmux"
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "A GHOST tmux session already exists. Stop it with: tmux kill-session -t ghost"
  exit 1
fi

tmux new-session -d -s "$SESSION" -n camera

tmux send-keys -t "$SESSION:camera" \
  "source /opt/ros/jazzy/setup.bash; source ~/ghost_venv/bin/activate; echo 'Camera viewer: ${CAMERA_URL}'; python ~/ghost_live_apriltag_pose_calibrated.py --device ${CAMERA_DEVICE} --tag-size ${TAG_SIZE}" C-m

tmux new-window -t "$SESSION" -n mh_tracker

tmux send-keys -t "$SESSION:mh_tracker" \
  "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; ros2 run ghost_sim_ros2 mh_tracker" C-m

tmux new-window -t "$SESSION" -n dashboard

tmux send-keys -t "$SESSION:dashboard" \
  "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; echo 'Visual dashboard: ${DASHBOARD_URL}'; ros2 run ghost_sim_ros2 mh_web_dashboard" C-m

tmux new-window -t "$SESSION" -n monitor

tmux send-keys -t "$SESSION:monitor" \
  "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; ros2 run ghost_sim_ros2 mh_monitor" C-m

tmux select-window -t "$SESSION:monitor"
echo "GHOST started. Controls: Ctrl+b then n/p to switch tabs, Ctrl+b then d to detach."
echo "Stop all: tmux kill-session -t ghost"
echo "Camera viewer: ${CAMERA_URL}"
echo "Visual dashboard: ${DASHBOARD_URL}"
tmux attach -t "$SESSION"
