# GHOST Portfolio Packet

## Executive Summary

GHOST is a ROS 2 autonomy project focused on target tracking when visual measurements are intermittent. The repository demonstrates a complete engineering loop: simulated development, live Raspberry Pi AprilTag capture, formal IMM tracking, heuristic MH side-by-side replay, hardware pipeline evidence plots, and a static replay dashboard that can be reviewed without ROS or external dependencies.

## Engineering Problem

Autonomy systems often lose direct target observations because of occlusion, sensor dropout, camera motion, or detection failures. GHOST addresses that problem by keeping a target-state estimate alive during gaps in AprilTag visibility and by exposing enough telemetry to inspect how the tracker behaves before, during, and after dropout.

## System Architecture

The project is organized around a ROS 2 target-tracking pipeline:

- AprilTag pose measurements publish target observations on `/ghost/vision/target_pose`.
- A formal IMM tracker estimates target state while switching probability mass between motion models.
- A heuristic MH tracker provides a contextual baseline for non-statistical side-by-side replay.
- Odom, status, future-hypothesis, and plot/export tools convert live bag data into reviewable evidence.
- Static documentation and dashboard assets make the final hardware run easy to inspect from GitHub or a local HTTP server.

## Hardware Pipeline Evidence

The final hardware replay artifact is the calibrated Raspberry Pi AprilTag bag `live_camera_calibrated_R_01`. The replay dashboard and plot page show the raw measurement stream, the formal IMM estimate, the heuristic MH estimate, tracker status transitions, and prediction behavior during target loss. This evidence validates live ROS 2 pipeline operation, topic rates, dropout/status telemetry, and replay tooling; report-grade real-world estimator accuracy validation is pending verified stationary measurement covariance R characterization.

## Key Metrics

| Metric | Value |
| --- | ---: |
| Final bag | `live_camera_calibrated_R_01` |
| Duration | `48.28 s` |
| Vision measurements | `655` |
| IMM odom samples | `1449` |
| MH odom samples | `1448` |
| IMM odom rate | `30.01 Hz` |
| MH odom rate | `29.99 Hz` |
| Camera pose rate | `13.57 Hz` |
| IMM `LIVE_IMM_TRACKING` statuses | `169` |
| IMM `LIVE_IMM_PREDICTION_ONLY` statuses | `2` |
| IMM `LIVE_IMM_DROPOUT_DEGRADED` statuses | `10` |
| Max IMM prediction-only steps | `77` |
| Max IMM measurement age | `2.849 s` |

## Why This Matters

For aerospace, autonomy, and robotics roles, this project shows practical ownership of problems that matter in real systems:

- Sensor-driven estimation with explicit handling of stale measurements.
- Pipeline evidence from a real hardware data source, not only a synthetic demo.
- Side-by-side qualitative replay of a formal model-based tracker and a heuristic baseline, with statistical comparison pending a dedicated harness.
- Reproducible evidence packaging through plots, reports, exported JSON, and a dependency-free static dashboard.
- Engineering discipline around safety boundaries: the package publishes target state and setpoint topics but does not arm or command a vehicle.

## Reproduce The Dashboard Locally

From the `ghost_sim_ros2` package directory:

```bash
cd docs && python3 -m http.server 8000 --bind 0.0.0.0
```

Then open:

```text
http://localhost:8000/GHOST_LIVE_REPLAY_DASHBOARD.html
```

The dashboard is fully static and reads local JSON from `docs/assets/ghost_live_dashboard/live_camera_calibrated_R_01_dashboard.json`.

## Review Links

- Detailed report: `docs/GHOST_PROJECT_REPORT.md`
- Final hardware bag plots: `docs/GHOST_LIVE_BAG_PLOTS.md`
- Live replay dashboard: `docs/GHOST_LIVE_REPLAY_DASHBOARD.html`
- Dashboard data exporter: `tools/export_live_dashboard_data.py`
- Hardware plot generator: `tools/plot_live_bag.py`
