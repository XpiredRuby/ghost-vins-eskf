# GHOST Hardware Calibration Evidence

Date: 2026-07-07

## Stationary AprilTag Measurement Noise

Stationary bags:
- `~/ghost_ws/bags/stationary_tag_R_02`
- `~/ghost_ws/bags/stationary_tag_R_03`

Measured stationary covariance:

Run R_02:
- samples: 489
- duration: 33.089 s
- std_x: 0.001181 m
- std_y: 0.000499 m
- R: [[0.000001394, 0.000000576], [0.000000576, 0.000000249]]

Run R_03:
- samples: 599
- duration: 40.541 s
- std_x: 0.001222 m
- std_y: 0.000330 m
- R: [[0.000001493, 0.000000374], [0.000000374, 0.000000109]]

Live tracker default now uses conservative scalar `measurement_std_m = 0.005`.

## Calibrated Live Hardware Run

Bag:
- `~/ghost_ws/bags/live_camera_calibrated_R_01`

Summary:
- duration: 48.280 s
- total messages: 6810
- camera pose: 655 messages, 13.57 Hz
- IMM odom: 1449 messages, 30.01 Hz
- MH odom: 1448 messages, 29.99 Hz

IMM status counts:
- LIVE_IMM_TRACKING: 169
- LIVE_IMM_PREDICTION_ONLY: 2
- LIVE_IMM_DROPOUT_DEGRADED: 10

MH status counts:
- VISIBLE - MEASUREMENT LOCK: 168
- HIDDEN - STATIONARY HOLD: 13

Dropout/recovery:
- max IMM prediction-only steps: 77
- max measurement age: 2.849 s

## Notes

The measured stationary sensor noise is near millimeter scale. The live trackers use a conservative 5 mm scalar measurement standard deviation to avoid overconfidence during real motion, tag angle changes, lighting variation, and handheld/demo conditions.
