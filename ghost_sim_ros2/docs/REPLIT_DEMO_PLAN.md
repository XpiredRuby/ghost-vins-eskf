# Replit Demo Plan

## Architecture

- Export a static `demo.json` from a preserved hardware trial directory with `ghost_sim_ros2/tools/export_demo_artifact.py`.
- Serve a small Flask app with static HTML, CSS, JavaScript, and the generated `demo.json`.
- Keep the app read-only. It replays recorded telemetry and does not connect to the camera, ROS graph, or live tracker.
- Use downsampled frames for browser performance. Keep raw trial logs as the source of record outside the hosted demo.

## Honesty Banner

Every demo view must show this persistent banner:

```text
Interactive replay of real hardware trial data - integration and telemetry demo. Estimator accuracy validation in progress.
```

## Claims Boundary

Do not claim validated accuracy until ground-truth grid validation exists.

Allowed claim: the demo replays real hardware integration telemetry from a recorded GHOST trial.

Disallowed claim: the demo proves estimator accuracy, production readiness, flight readiness, or general robustness.

## Export Command

```bash
cd ~/ghost_ws/src/ghost-vins-eskf/ghost_sim_ros2
python3 tools/export_demo_artifact.py "$TRIAL_DIR" --hz 10 --out "$TRIAL_DIR/demo.json"
```

The exported metadata must retain:

- `demo_status: integration_telemetry_demo`
- `accuracy_validation_status: pending_ground_truth_grid_validation`
- `source_trial_dir`
- `generated_at_utc`
