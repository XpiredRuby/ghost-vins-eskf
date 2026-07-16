# Browser-Guided GHOST Physical Validation Launcher

`guided_hardware_launcher.py` replaces the four-terminal manual workflow with one detached supervisor and one browser page.

## What it starts

The supervisor starts and owns only its own child process groups:

1. calibrated AprilTag camera publisher with a 5 Hz annotated MJPEG preview;
2. formal IMM tracker;
3. GHOST-MH tracker;
4. trial recorder;
5. browser cue conductor.

It waits for the preview and conductor health endpoints before reporting the browser URL. When the browser sequence finishes or is rejected, it stops the recorder first, then the conductor, trackers, and camera. Logs, recorder files, conductor events, state, and a final launcher summary remain in the run directory.

## Before starting

Stop any manually launched camera publisher, IMM tracker, MH tracker, or trial recorder. The launcher refuses to start when conflicting processes are detected. `--force` only bypasses that refusal; it never kills or adopts existing processes and should not be used for the normal workflow.

## Start

From the repository:

```bash
python3 ghost_sim_ros2/tools/guided_hardware_launcher.py start
```

The command returns after startup and prints:

```text
browser_url=http://<pi-hostname>.local:8765
run_dir=/home/xpired/ghost_trials/physical_validation_20260711T183400Z/browser_guided_runs/<UTC_TIMESTAMP>
supervisor_pid=<PID>
```

The launching terminal may then be closed. Open the printed URL on a computer connected to the same network, select **Arm audio**, confirm the live preview, and select **Start cues**.

When `.local` name resolution is unavailable, provide the Pi address explicitly:

```bash
python3 ghost_sim_ros2/tools/guided_hardware_launcher.py start --public-host <PI_IP_ADDRESS>
```

## Browser sequence

The predeclared sequence guides and times:

- centered alignment and baseline;
- webcam left movement and hold;
- return to center;
- webcam right movement and hold;
- return to center;
- closer movement and hold;
- return to center;
- farther movement and hold;
- return to center;
- preparation for occlusion;
- exactly 2.0 seconds covering the complete AprilTag only;
- reveal, recovery hold, and post-roll.

Do not cover the webcam lens during the short-dropout trial. Lens blackout can require several seconds for camera/detector recovery and can exceed the configured 3.0-second GHOST-MH occlusion envelope.

## Focused recovery profiles

Use these only when the full guided sequence identifies incomplete distance coverage:

```bash
python3 ghost_sim_ros2/tools/start_distance_only_run.py
python3 ghost_sim_ros2/tools/start_closer_only_run.py
```

The distance-only profile retests closer and farther holds. The closer-only profile uses a smaller approach after a failed closer segment. Both preserve the same single-browser workflow and supervisor ownership rules. The launcher selects the correct post-processor from the plan condition and writes `distance_only_summary.json` or `closer_only_summary.json` automatically.

## Status

```bash
python3 ghost_sim_ros2/tools/guided_hardware_launcher.py status
```

This reports the durable lifecycle state, browser URL, supervisor state, child PIDs, and observed child health.

## Stop manually

```bash
python3 ghost_sim_ros2/tools/guided_hardware_launcher.py stop
```

The live supervisor handles graceful shutdown. If the supervisor is no longer alive, the fallback stop targets only process-group IDs saved in that run's state file; it never uses a broad `pkill`.

## Dry run

The following command prints the complete cue plan and child command vectors without touching ROS, the camera, ports, or processes:

```bash
python3 ghost_sim_ros2/tools/guided_hardware_launcher.py dry-run --public-host ghost-pi.local
```

## Evidence layout

Each run is stored beneath:

```text
/home/xpired/ghost_trials/physical_validation_20260711T183400Z/browser_guided_runs/<UTC_TIMESTAMP>/
```

Key files include:

```text
launcher_state.json
launcher_summary.json
randomized_trial_order.csv
logs/
recorder_trials/
trial_directories/guided_relative_motion_dropout_01/conductor_plan.json
trial_directories/guided_relative_motion_dropout_01/conductor_events.jsonl
```

## Claim limits

This workflow provides:

- calibrated camera pose-stream evidence;
- timed relative left/right/closer/farther response coverage;
- measured vision-gap, prediction, reset, and reacquisition evidence;
- synchronized conductor-event and tracker-recorder logs.

The hand-guided positions are approximate. They do **not** establish absolute position accuracy, grid RMSE, or metrology-grade ground truth. Recorder timestamps—not the browser cue duration alone—determine dropout acceptance.
