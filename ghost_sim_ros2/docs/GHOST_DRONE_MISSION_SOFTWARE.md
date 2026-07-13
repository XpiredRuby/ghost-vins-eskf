# GHOST Drone/Robot Mission Software

## What GHOST is

GHOST is a ROS 2 Jazzy **GPS-denied, occlusion-aware target tracking and prediction system for a mobile drone/robot observer**.

The observer receives target measurements only when its simulated camera has:

- sufficient range;
- target bearing inside the camera field of view; and
- unobstructed line of sight through the mapped environment.

When a building blocks the target, measurements stop. The formal IMM and GHOST-MH trackers continue estimating target motion, while the observer guidance system moves around the blocking obstacle toward a collision-free vantage point and attempts reacquisition.

The mission uses a local frame anchored at simulation start. It does **not** use GPS target measurements. Simulated target truth is published only for visualization and evaluation; it is not consumed by the tracker or guidance controller.

## One-command demonstration

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2 --symlink-install
source install/setup.bash

ros2 launch ghost_sim_ros2 ghost_drone_mission.launch.py
```

Open the live mission dashboard from a computer on the same network:

```text
http://<RASPBERRY_PI_IP>:8088
```

The dashboard shows:

- drone/robot observer pose and trail;
- target truth and visible camera measurements;
- camera field of view and visible/blocked line of sight;
- mapped buildings and collision-free navigation path;
- formal IMM estimate and futures;
- GHOST-MH estimate and ranked future hypotheses;
- visible, hidden, prediction, and reacquisition states;
- mission acceptance metrics.

### Select the formal IMM for guidance

GHOST-MH is the default navigation source. The formal IMM can be selected without changing code:

```bash
ros2 launch ghost_sim_ros2 ghost_drone_mission.launch.py tracker_source:=imm
```

### Save machine-readable mission evidence

```bash
ros2 launch ghost_sim_ros2 ghost_drone_mission.launch.py \
  dashboard_enabled:=false \
  mission_duration_s:=32.0 \
  metrics_path:=/tmp/ghost_drone_mission_metrics.json
```

## System architecture

```text
Deterministic target trajectory + local obstacle map
                         |
                         v
        camera range/FOV/line-of-sight sensor model
                         |
               /ghost/vision/target_pose
                   |                 |
                   v                 v
          Formal IMM tracker   GHOST-MH tracker
                   |                 |
                   +--------+--------+
                            |
                 selected target estimate
                            |
           bounded hidden-state guidance target
                            |
     named-obstacle vantage selection + A* path planning
                            |
       speed/acceleration/yaw limits + final safety gate
                            |
                    observer dynamics
                            |
             line-of-sight and reacquisition loop
```

## Implemented software components

### Mission simulator

`mission_simulator.py`

- deterministic local-frame target trajectory;
- rectangular building map and world boundaries;
- observer/drone planar dynamics;
- configurable camera range, field of view, and measurement noise;
- true segment-versus-obstacle line-of-sight gating;
- camera measurements on the existing `/ghost/vision/target_pose` interface;
- target truth, observer odometry, markers, and mission status.

### Formal IMM and GHOST-MH

The existing tracker cores remain the estimators. The software mission enables an explicit signed-local-coordinate option; the hardware camera default remains unchanged.

The formal IMM and GHOST-MH run simultaneously and publish:

```text
/ghost/tracker_imm/target_odom
/ghost/tracker_imm/futures_json
/ghost/tracker_imm/status

/ghost/tracker_mh/target_odom
/ghost/tracker_mh/futures_json
/ghost/tracker_mh/status
```

### Observer guidance

`observer_guidance.py`

- uses GHOST-MH by default or the formal IMM by parameter;
- maintains a configurable target standoff while visible;
- exits the initial observation hold immediately when line of sight is lost;
- keeps the full tracker hypotheses for analysis and display;
- uses a bounded last-visible motion prediction for safety-critical navigation;
- identifies the obstacle that caused line-of-sight loss;
- selects a clear obstacle-corner vantage point;
- plans an inflated-obstacle A* route;
- limits observer speed, acceleration, and yaw rate;
- rejects any next-step command that would violate collision clearance.

### Mission evaluator

`mission_evaluator.py`

The evaluator measures actual runtime behavior. It does not hard-code a passing result. The default mission passes only when all of these are observed:

- camera measurements received;
- at least one obstacle-caused line-of-sight loss;
- formal IMM outputs during occlusion;
- GHOST-MH outputs during occlusion;
- hidden-target vantage reposition used;
- target reacquired;
- observer moved at least one metre;
- zero observer collisions;
- zero boundary violations;
- mission completion.

### Live dashboard

`mission_dashboard.py`

A dependency-light standard-library HTTP server exposes a responsive 2D mission-control dashboard and `/api/state` JSON endpoint. It runs headlessly on the Raspberry Pi.

## Final deterministic validation

Evidence file: [`GHOST_DRONE_MISSION_VALIDATION.json`](GHOST_DRONE_MISSION_VALIDATION.json)

| Metric | Final observed value |
|---|---:|
| Mission duration | `32.0816 s` |
| Obstacle-caused LOS losses | `2` |
| Longest measured LOS loss | `9.5332 s` |
| Reacquisitions | `2` |
| Formal IMM outputs during occlusion | `456` |
| GHOST-MH outputs during occlusion | `457` |
| Hidden-vantage guidance commands | `291` |
| Observer distance travelled | `12.3016 m` |
| Final target-observer separation | `2.3379 m` |
| Observer collisions | `0` |
| Boundary violations | `0` |
| Safety-gate interventions | `0` |
| Overall acceptance | **PASS** |

The measured synthetic-truth errors for this long, turning, obstacle-occlusion scenario are retained in the JSON evidence. They are not hidden or presented as hardware accuracy.

## Simulation-to-hardware connection

The same tracker input and output interfaces are used by both paths:

```text
Software mission sensor  ----\
                              > /ghost/vision/target_pose -> IMM + GHOST-MH
Pi camera + AprilTag proxy --/
```

The software mission demonstrates the intended drone/robot operational context. The Raspberry Pi camera campaign separately demonstrates that the real camera-to-ROS-to-tracker pipeline, prediction-only behavior, and reacquisition work on hardware.

## Claim boundaries

### Supported

- GPS-free target sensing in a deterministic local-frame software mission;
- obstacle-derived line-of-sight loss;
- concurrent formal IMM and multi-hypothesis prediction;
- obstacle-aware mobile-observer navigation and reacquisition;
- deterministic machine-readable acceptance testing;
- Raspberry Pi camera/AprilTag proxy hardware validation of the tracking pipeline.

### Not claimed

- GPS-denied self-localization or SLAM;
- real drone flight or PX4 flight-control integration;
- flight certification or production safety;
- hardware ground-truth trajectory accuracy;
- general semantic object detection beyond the current camera-target interface;
- statistical superiority from the deferred 55-trial physical campaign.
