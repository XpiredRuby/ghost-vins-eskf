# GHOST Drone Mission Implementation Report

## Status

**Implemented and validated.**

GHOST now includes a complete software mission for a mobile drone/robot-style observer that tracks a moving target in a local GPS-denied environment, predicts during building occlusion, navigates around the blocking obstacle, and reacquires the target.

This work extends the existing tracking project; it does not replace the physical Raspberry Pi camera evidence.

## Final software architecture

1. `mission_simulator.py`
   - deterministic target mission;
   - local map and rectangular buildings;
   - planar observer dynamics;
   - camera range/FOV/obstacle line-of-sight model;
   - measurement noise;
   - existing `/ghost/vision/target_pose` tracker interface;
   - truth, observer, marker, visibility, and mission topics.

2. Existing `formal_imm_tracker.py`
   - side-by-side formal IMM estimate and futures;
   - explicit signed-local-coordinate option for simulation;
   - hardware camera default remains unsigned-forward.

3. Existing `mh_tracker.py` and `analysis/ghost_mh_mode_bank.py`
   - persistent physical motion hypotheses during occlusion;
   - signed-local-coordinate support only when explicitly enabled;
   - 15-second software-mission occlusion horizon;
   - original hardware defaults preserved.

4. `observer_guidance.py`
   - GHOST-MH or formal IMM selectable as navigation source;
   - visible-target standoff control;
   - immediate response to line-of-sight loss;
   - bounded last-visible prediction for guidance safety;
   - named blocking-obstacle corner selection;
   - obstacle-inflated A* planning;
   - speed, acceleration, and yaw limits;
   - final one-step collision safety gate.

5. `mission_evaluator.py`
   - machine-readable measured acceptance;
   - actual occlusion durations;
   - tracker-output counts during loss;
   - observer travel and hidden-vantage command counts;
   - collision and boundary checks;
   - reacquisition and completion checks;
   - synthetic-truth error reporting.

6. `mission_dashboard.py`
   - headless standard-library web server;
   - responsive 2D mission map;
   - target, observer, camera FOV, buildings, line of sight, path, IMM, MH, and futures;
   - health and state JSON APIs.

7. `launch/ghost_drone_mission.launch.py`
   - starts the complete system with one ROS 2 launch command.

## Files added

```text
ghost_sim_ros2/ghost_sim_ros2/ghost_world.py
ghost_sim_ros2/ghost_sim_ros2/mission_simulator.py
ghost_sim_ros2/ghost_sim_ros2/observer_guidance.py
ghost_sim_ros2/ghost_sim_ros2/mission_evaluator.py
ghost_sim_ros2/ghost_sim_ros2/mission_dashboard.py
ghost_sim_ros2/config/ghost_drone_mission.yaml
ghost_sim_ros2/launch/ghost_drone_mission.launch.py
ghost_sim_ros2/test/test_ghost_world.py
ghost_sim_ros2/test/test_signed_mh_local_frame.py
ghost_sim_ros2/docs/GHOST_DRONE_MISSION_SOFTWARE.md
ghost_sim_ros2/docs/GHOST_DRONE_MISSION_VALIDATION.json
ghost_sim_ros2/docs/GHOST_DRONE_MISSION_IMPLEMENTATION_REPORT.md
```

## Existing files intentionally updated

```text
ghost_sim_ros2/ghost_sim_ros2/formal_imm_tracker.py
ghost_sim_ros2/ghost_sim_ros2/mh_tracker.py
ghost_sim_ros2/analysis/ghost_mh_mode_bank.py
ghost_sim_ros2/setup.py
ghost_sim_ros2/package.xml
ghost_sim_ros2/README.md
README.md
```

The physical-validation files `apriltag_ros_only.py` and `tools/trial_conductor.py` were not reverted.

## Build and test evidence

### Syntax

All new and modified Python modules passed `compileall` / `py_compile`.

### Focused tests

```text
8 passed in 0.39 s
```

Coverage includes:

- segment/rectangle visibility geometry;
- FOV and range rejection;
- obstacle-inflated A* paths;
- speed, acceleration, and yaw constraints;
- deterministic target mission behavior;
- obstacle occlusion and reappearance;
- signed-local-coordinate GHOST-MH behavior;
- preserved hardware default rejection behavior.

### Full package regression

```text
214 passed in 204.56 s
```

### ROS 2 build

```text
Summary: 1 package finished
```

The package built successfully using:

```bash
colcon build --packages-select ghost_sim_ros2 --symlink-install
```

### Dashboard smoke test

```text
health {"status":"ok"}
missing_keys []
world_obstacles 2
imm_present True
mh_present True
```

## Final mission acceptance evidence

Source: `docs/GHOST_DRONE_MISSION_VALIDATION.json`

| Acceptance item | Result |
|---|---:|
| Camera measurements received | PASS |
| Obstacle occlusion observed | PASS |
| Formal IMM predicted during occlusion | PASS |
| GHOST-MH predicted during occlusion | PASS |
| Hidden-vantage reposition used | PASS |
| Observer navigated | PASS |
| Target reacquired | PASS |
| Observer collision-free | PASS |
| Observer stayed inside bounds | PASS |
| Mission completed | PASS |

### Final measured values

| Metric | Value |
|---|---:|
| Mission duration | `32.0815796852 s` |
| Obstacle occlusion count | `2` |
| Longest occlusion | `9.5332050323 s` |
| Reacquisition count | `2` |
| IMM outputs during occlusion | `456` |
| GHOST-MH outputs during occlusion | `457` |
| Hidden-vantage commands | `291` |
| Navigation commands | `343` |
| Observer distance travelled | `12.3016124975 m` |
| Final target-observer separation | `2.3379028644 m` |
| Maximum commanded speed | `1.15 m/s` |
| Collisions | `0` |
| Boundary violations | `0` |
| Safety interventions | `0` |
| Overall result | **PASS** |

Synthetic-truth error values remain in the JSON evidence. They are reported rather than hidden, but they are not hardware-accuracy claims.

## Exact run command

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
source install/setup.bash
ros2 launch ghost_sim_ros2 ghost_drone_mission.launch.py
```

Dashboard:

```text
http://<RASPBERRY_PI_IP>:8088
```

## Recruiter-safe description

> Built GHOST, a ROS 2 GPS-denied occlusion-aware target tracking and prediction system for a mobile drone/robot observer. Integrated a formal IMM and multi-hypothesis tracker with camera line-of-sight sensing, obstacle-aware A* vantage planning, bounded guidance, collision checks, live mission visualization, machine-readable acceptance testing, and Raspberry Pi camera validation.

## Remaining limitations

- Observer self-pose is available from the software simulator; SLAM/VIO is not implemented.
- The observer is planar and kinematic, not a six-degree-of-freedom aircraft model.
- No PX4, HIL, actuator, aerodynamic, or real flight-control integration is claimed.
- Target sensing uses the existing position-measurement interface; semantic object detection remains outside this mission layer.
- The formal 55-trial physical campaign remains deferred.
- Long open-loop prediction errors can grow during aggressive target turns; the navigation system therefore uses bounded last-visible prediction for guidance while retaining full hypotheses for analysis.
