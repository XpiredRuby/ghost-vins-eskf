# GHOST-X Predeclared Scenario Catalog

This catalog freezes the required nominal and fault scenario families before formal campaign collection. Exact geometry, truth method, uncertainty, speeds, durations, and randomization are finalized in G4 protocols without removing required scenario families.

## Common requirements

Every scenario record shall include:

- scenario and trial identifiers;
- software commit and configuration hash;
- calibration hash;
- estimator input hash;
- truth source and uncertainty;
- source/receipt/publication timestamps;
- accepted, invalid, or failed disposition with reason;
- IMM, GHOST-MH, and baseline outputs from identical inputs;
- resource and fault events where applicable.

## Nominal and maneuver scenarios

### N-STAT — Stationary

Target remains fixed for a predeclared interval at controlled range and orientation.

Required outputs: bias, covariance, drift, autocorrelation, visible RMSE, status stability, CPU/timing.

### N-CV — Constant velocity

Target traverses a straight measured path at approximately constant speed.

Required outputs: position/velocity RMSE, lag, covariance, model probabilities, baseline comparison.

### N-ACCEL — Acceleration and deceleration

Target follows a straight measured path with predeclared acceleration and braking regions.

Required outputs: transient error, mode transition behavior, velocity error, recovery.

### N-TURN — Coordinated turn or arc

Target follows a repeatable arc or corner trajectory with declared geometry.

Required outputs: turn tracking, hypothesis ranking, endpoint error, mode transition delay.

### N-STOPGO — Stop and go

Target alternates motion and stationary holds.

Required outputs: stationary detection, false motion, hold stability, restart response.

### N-ABRUPT — Abrupt maneuver

Target executes a predeclared direction or speed change.

Required outputs: peak error, recovery time, false confidence, hypothesis coverage.

### N-PARTIAL-OCC — Partial occlusion

Tag or target is partially blocked while some detections may continue intermittently.

Required outputs: detection acceptance pattern, false-track rate, covariance behavior, status.

### N-FULL-OCC — Complete occlusion

Target becomes fully hidden for predeclared durations, including at least short and two-second classes.

Required outputs: error growth, covariance growth, hypotheses, prediction-only status, reacquisition.

### N-REENTRY — Repeated re-entry

Target repeatedly leaves and re-enters valid camera visibility.

Required outputs: repeated reacquisition, track continuity, reset count, stale-state behavior.

### N-DRONE-CORNER — Autonomous observer corner navigation

Software observer tracks a target around known obstacles, loses LOS, predicts, repositions, and reacquires.

Required outputs: observer path, collisions, boundary violations, hidden commands, estimator outputs, reacquisitions.

## Fault scenarios

### F-CAMERA-DISCONNECT

Remove or disable the camera data source.

Expected behavior: measurement loss detected, prediction/degraded status emitted, no fabricated measurements, controlled recovery after source restoration.

### F-FROZEN-MEASUREMENT

Repeat an unchanged measurement with advancing receipt time.

Expected behavior: freeze detected or reflected in status/counters; estimator must not silently report normal confidence indefinitely.

### F-DUPLICATE

Replay duplicate timestamped measurements.

Expected behavior: duplicate counted/rejected according to contract; deterministic output.

### F-FALSE-DETECTION

Inject plausible but incorrect target measurements.

Expected behavior: gating/status response recorded; persistent false lock constrained and reported.

### F-COVARIANCE

Inject nonfinite, asymmetric, non-PSD, zero, or unrealistically large covariance.

Expected behavior: validation failure or explicit bounded fallback; no silent use of corrupt covariance.

### F-LATENCY

Add fixed and variable measurement delay.

Expected behavior: measurement age and latency reported; stale threshold and degraded behavior verified.

### F-OUT-OF-SEQUENCE

Deliver valid measurements with older source timestamps after newer data.

Expected behavior: deterministic reject, reorder, or explicit OOS handling according to G2 contract.

### F-NODE-RESTART

Restart estimator or sensor nodes during a trial.

Expected behavior: restart event recorded, validity reset, deterministic reinitialization, recovery measured.

### F-CPU-SATURATION

Apply controlled background CPU load.

Expected behavior: latency/jitter/resource degradation quantified; missed deadlines and thermal state reported.

### F-NETWORK

Introduce DDS/network delay, loss, or degraded QoS path.

Expected behavior: liveliness/deadline/status behavior and recovery measured.

### F-PARAMETER

Run with a deliberate configuration or calibration identifier mismatch.

Expected behavior: mismatch detected before acceptance or clearly labeled in evidence.

### F-LIGHTING

Reduce illumination or introduce glare within a controlled procedure.

Expected behavior: measurement availability and quality degradation measured; no unsupported camera robustness claim.

## Collection order and anti-bias rules

- Scenario parameters are frozen before formal collection.
- Estimator labels may be blinded in analysis where practical.
- Trial order is randomized or balanced where operator constraints allow.
- Failed and invalid runs are retained with reason codes.
- Thresholds are not changed after observing formal results without a discrepancy record.
- Identical accepted measurement and truth streams are used for all compared estimators.
