# GHOST Project Report

_Last synchronized with repository main after the controlled covariance, ground-truth grid, paired statistics, and static demo tooling were merged._

## 1. Executive summary

GHOST is a Raspberry Pi and ROS 2 vision-tracking project for estimating a target's two-dimensional position and velocity when AprilTag measurements are intermittent. The current hardware pipeline runs two trackers from the same measurement stream:

1. a formal Interacting Multiple Model (IMM) estimator; and
2. a bounded heuristic multi-hypothesis (MH) tracker used as an operational comparison baseline.

The preserved hardware run demonstrates live measurement ingestion, simultaneous tracker output near 30 Hz, explicit prediction-only behavior during target loss, degraded-dropout status, and recovery after measurements return.

The repository now also contains predeclared controlled measurement-covariance collection, measured-grid accuracy analysis, paired statistical comparison, and static demo export tooling. Those tools are implemented, but the decisive new physical data have not yet been collected.

**Evidence boundary:** current hardware evidence validates integration, timing, telemetry, dropout-state behavior, and replay. It does not yet establish report-grade tracking accuracy, statistically proven tracker superiority, production robustness, closed-loop control, or flight readiness.

## 2. Engineering problem

A vision detector produces observations only while a target can be detected. During occlusion, motion blur, lighting degradation, or dropped frames, a useful tracking system must:

- propagate a state estimate without pretending that a measurement exists;
- represent increasing uncertainty;
- expose the age of the last valid observation;
- constrain the duration and interpretation of open-loop prediction;
- recover when measurements return;
- preserve enough telemetry to audit the behavior afterward.

GHOST treats dropout as an estimator state rather than hiding it behind a smooth trajectory plot.

## 3. Current system architecture

```text
camera + AprilTag
        |
        v
/ghost/vision/target_pose
        |
        +-----------------------------+
        |                             |
        v                             v
formal IMM tracker              heuristic GHOST-MH tracker
        |                             |
        v                             v
odom + futures + status         odom + futures + status
        \                             /
         +-- recorder / plots / replay / analysis --+
```

### 3.1 Vision measurement

The AprilTag publisher provides a timestamped two-dimensional target position through:

```text
/ghost/vision/target_pose
```

The live covariance path supports a full symmetric measurement matrix:

```text
R = [[R_xx, R_xy],
     [R_xy, R_yy]]
```

Telemetry has confirmed that both trackers receive and report the expected full-`R` metadata. This verifies plumbing, not the correctness of the covariance values.

### 3.2 Formal IMM tracker

The IMM maintains multiple motion-model filters, mixes their states and covariances, updates model probabilities from the measurement likelihoods, and combines the model-conditioned outputs into one estimate.

Live outputs:

```text
/ghost/tracker_imm/target_odom
/ghost/tracker_imm/futures_json
/ghost/tracker_imm/status
```

The live configuration distinguishes smooth constant-velocity behavior from a higher-process-noise maneuver model. Its mode values are valid IMM probabilities.

### 3.3 GHOST-MH tracker

The heuristic MH tracker provides bounded candidate futures and operational context during temporary target loss.

Live outputs:

```text
/ghost/tracker_mh/target_odom
/ghost/tracker_mh/futures_json
/ghost/tracker_mh/status
```

Its candidate rankings are **relative hypothesis weights**, not calibrated probabilities. It is not presented as a replacement for a formal Bayesian estimator.

## 4. Hardware integration evidence

The preserved run is:

```text
live_camera_calibrated_R_01
```

| Metric | Result |
|---|---:|
| Duration | `48.280 s` |
| Vision measurements | `655` |
| Camera pose rate | `13.57 Hz` |
| IMM odometry rate | `30.01 Hz` |
| MH odometry rate | `29.99 Hz` |
| IMM tracking status samples | `169` |
| IMM prediction-only status samples | `2` |
| IMM dropout-degraded status samples | `10` |
| MH visible-lock status samples | `168` |
| MH hidden-hold status samples | `13` |
| Maximum IMM prediction-only steps | `77` |
| Maximum IMM measurement age | `2.849 s` |

The run verifies that the camera measurement source and both trackers operated together in real time and emitted reviewable state, status, and future-path telemetry. During target loss, the IMM entered prediction-only and dropout-degraded states before returning to tracking after reacquisition.

## 5. Measurement covariance status

Earlier stationary recordings suggested millimeter-scale raw measurement variation, but they were not collected under the final predeclared protocol. They informed candidate values only.

The current controlled protocol is committed at:

```text
docs/CONTROLLED_R_COLLECTION_PROTOCOL.md
```

It fixes the following before data collection:

- exactly `90 s` of recording;
- analysis only over seconds `15–75`;
- no post-hoc trimming;
- camera-control readback before, after setting, and after the trial;
- raw `R_xx`, `R_xy`, and `R_yy`;
- correlation coefficient;
- fixed sub-window stability checks over `15–35`, `35–55`, and `55–75 s`.

Required status until that trial is completed:

```text
R status: CONTROLLED_R_PREDECLARED_PENDING_COLLECTION
Accuracy status: DOES_NOT_VALIDATE_TRACKER_ACCURACY
```

## 6. Accuracy-validation status

Ground-truth grid tooling is implemented in:

```text
ghost_sim_ros2/analysis/grid_validation_analysis.py
```

The physical protocol requires 5 or 6 non-collinear measured points, variation in both axes, the same locked camera setup as the controlled covariance trial, and 10 seconds stationary per point.

Planned outputs include:

- per-point mean and standard deviation;
- `dx` and `dy` bias;
- Euclidean point error;
- aggregate bias;
- RMSE;
- mean error;
- maximum error;
- sample count and sample rate.

No grid results are reported because the physical trial has not yet been run.

## 7. IMM/MH comparison status

A paired comparison harness is implemented in:

```text
ghost_sim_ros2/analysis/statistical_comparison.py
```

It reports paired median errors, median MH-minus-IMM difference, error reduction, bootstrap confidence intervals, and a Wilcoxon signed-rank result when SciPy is available.

This closes the software-tooling gap but does not establish performance superiority. Repeated paired hardware trials with measured truth are still required.

## 8. Evidence packaging and replay

The project includes:

- split IMM and MH futures logs;
- hardware-bag plotting;
- machine-readable JSON export;
- a dependency-free HTML replay dashboard;
- project and portfolio reports;
- a static hosted-demo export plan.

The replay dashboard presents raw measurements, both tracker estimates, IMM mode probabilities, status, measurement age, prediction-only steps, and future tails. It is an integration and telemetry artifact. It is not an accuracy-validation artifact.

## 9. Software engineering

The repository includes:

- ROS 2 Jazzy nodes and launch files;
- portable estimator components;
- unit tests for covariance, IMM, stationary gating, grid analysis, statistical comparison, and demo export;
- GitHub Actions for Python tests and the portable C++ build;
- runbooks for collection and replay;
- explicit status strings and claims boundaries.

Trial recording writes separate IMM and MH future logs so one tracker cannot silently overwrite the other's evidence.

## 10. GNC relevance and limits

GHOST currently demonstrates the navigation/estimation core of a GNC workflow:

- sensor measurement handling;
- state and covariance estimation;
- multiple-model interaction;
- uncertainty propagation;
- stale-measurement supervision;
- downstream ROS 2 state/setpoint interfaces.

The current hardware package does not contain validated closed-loop guidance and control. It does not arm or command a vehicle and has not been flight tested. A future closed-loop simulation should connect the target estimate to a bounded guidance law, controller, vehicle dynamics, and safe-hold behavior during prolonged dropout.

## 11. Reproducibility

Build the ROS 2 package:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2 --symlink-install
source install/setup.bash
```

Run the software-only pipeline:

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

Serve the static hardware replay:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf/ghost_sim_ros2/docs
python3 -m http.server 8000 --bind 0.0.0.0
```

Open:

```text
http://localhost:8000/GHOST_LIVE_REPLAY_DASHBOARD.html
```

## 12. Next experimental sequence

1. Execute the predeclared controlled covariance trial.
2. Reject or accept the run using the documented criteria.
3. Keep the camera fixed and execute the measured ground-truth grid.
4. Publish covariance, stability, bias, RMSE, mean error, maximum error, and repeatability.
5. Execute repeated visible and occluded trajectories under fixed scenario definitions.
6. Apply the paired statistical harness.
7. Add runtime, CPU, memory, and thermal evidence on the Raspberry Pi.
8. Use only the resulting validated metrics in the public demo and resume material.

## 13. Safe conclusion

GHOST currently provides strong evidence of end-to-end robotics estimation integration: real camera measurements, ROS 2 transport, formal and heuristic trackers, explicit dropout supervision, and reproducible replay tooling.

The project will cross from hardware-integrated prototype to quantitatively validated estimator only after the predeclared controlled covariance and ground-truth trials are completed.
