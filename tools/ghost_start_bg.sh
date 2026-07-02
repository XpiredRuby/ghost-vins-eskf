#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="$HOME/ghost_logs/live"
PID_DIR="$HOME/ghost_logs/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

stop_one() {
  local name="$1"
  local pid_file="$PID_DIR/${name}.pid"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.3
    fi
    rm -f "$pid_file"
  fi
}

stop_one camera
stop_one mh_tracker
stop_one trial_recorder
stop_one mh_monitor
stop_one mh_web_dashboard

start_one() {
  local name="$1"
  shift
  local log="$LOG_DIR/${name}.log"
  echo "Starting $name -> $log"
  nohup bash -lc "$*" >"$log" 2>&1 &
  echo $! > "$PID_DIR/${name}.pid"
}

start_one camera "source /opt/ros/jazzy/setup.bash; source ~/ghost_venv/bin/activate; exec python ~/ghost_live_apriltag_pose_calibrated.py --device /dev/video0 --tag-size 0.10"
start_one mh_tracker "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; exec ros2 run ghost_sim_ros2 mh_tracker"
start_one trial_recorder "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; exec ros2 run ghost_sim_ros2 trial_recorder"
start_one mh_monitor "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; exec ros2 run ghost_sim_ros2 mh_monitor"
start_one mh_web_dashboard "source /opt/ros/jazzy/setup.bash; cd ~/ghost_ws; source install/setup.bash; exec ros2 run ghost_sim_ros2 mh_web_dashboard"

sleep 2

echo
echo "GHOST started."
echo "Camera viewer:      http://192.168.1.142:8081"
echo "Visual dashboard:  http://192.168.1.142:8090"
echo "Trial logs:        ~/ghost_logs/trials/<timestamp>/"
echo
echo "Check status: ~/ghost_status.sh"
echo "Stop all:     ~/ghost_stop.sh"
