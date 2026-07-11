# GHOST Project Report

_Last synchronized after the formal-IMM closed-loop GNC SIL, hardened controlled-R pipeline, paired hardware campaign, public Pages site, and expanded CI were merged._

## 1. Executive summary

GHOST is a Raspberry Pi and ROS 2 target-estimation project for intermittent AprilTag visibility. The live hardware pipeline runs two trackers from the same measurement stream:

1. a formal Interacting Multiple Model (IMM) estimator; and
2. a bounded heuristic multi-hypothesis (MH) tracker used as an operational comparison baseline.

The preserved hardware run demonstrates live measurement ingestion, simultaneous tracker output near 30 Hz, explicit prediction-only behavior during target loss, degraded-dropout status, and recovery after measurements return.

The repository also contains a deterministic software-in-the-loop GNC harness that connects the same formal IMM to relative-standoff guidance, an acceleration-limited velocity controller, first-order actuator lag, follower dynamics, and a three-state `TRACKING` / `PREDICTION` / `SAFE_HOLD` supervisor.

The physical validation infrastructure is predeclared and implemented: hardened controlled covariance collection, fixed-window and sub-window analysis, measured-grid accuracy analysis, a 55-trial paired IMM/MH campaign, manifest validation, bootstrap confidence intervals, and Wilcoxon reporting.

**Evidence boundary:** current hardware evidence validates integration, timing, telemetry, dropout-state behavior, and replay. Current GNC evidence validates deterministic software-only estimator-guidance-controller-plant integration. Neither establishes physical tracking accuracy, hardware controller performance, PX4/HIL integration, vehicle command, flight readiness, or flight testing.

## 2. Engineering problem

A vision detector produces observations only while a target can be detected. During occlusion, blur, lighting degradation, or dropped frames, a useful tracking and autonomy stack must:

- propagate state without pretending that a measurement exists;
- represent increasing uncertainty;
- expose the age of the last valid observation;
- constrain the duration and interpretation of open-loop prediction;
- transition to a safe behavior when prediction becomes too stale;
- recover when measurements return;
- preserve enough telemetry to audit the behavior afterward.

GHOST treats dropout as an estimator and supervisor state rather than hiding it behind a smooth trajectory plot.

## 3. Hardware estimation architecture

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

The AprilTag publisher provides timestamped two-dimensional target position through:

```text
/ghost/vision/target_pose
```

The live covariance path supports a full symmetric measurement matrix:

```text
R = [[R_xx, R_xy],
     [R_xy, R_yy]]
```

Telemetry confirms that both trackers receive and report the expected full-`R` metadata. This verifies plumbing, not the correctness of the covariance values.

### 3.2 Formal IMM tracker

The IMM maintains multiple motion-model filters, mixes states and covariances, updates mode probabilities from measurement likelihoods, and combines model-conditioned outputs into one estimate.

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

Its rankings are **relative hypothesis weights**, not calibrated probabilities. It is not presented as a replacement for a formal Bayesian estimator.

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

## 5. Closed-loop GNC software-in-the-loop

### 5.1 Architecture

```text
synthetic target truth
        |
noisy / intermittent position measurements
        |
formal GHOST IMM
        |
relative-standoff guidance
        |
acceleration-limited velocity controller
        |
first-order actuator model + follower dynamics
        |
closed-loop follower state
```

The harness is implemented in:

```text
ghost_sim_ros2/analysis/closed_loop_gnc_sil.py
```

The guidance law is:

```text
r     = p_target_est - p_follower
e_r   = ||r|| - r_standoff
v_des = v_target_est + sat(k_r * e_r) * r / ||r||
```

The controller is:

```text
a_cmd = sat(k_v * (v_des - v_follower))
```

The actuator is modeled as a first-order response before the follower dynamics integrate achieved acceleration.

### 5.2 Supervisor

- `TRACKING`: a measurement is available; guidance uses the measurement-updated IMM estimate.
- `PREDICTION`: measurement is absent but age is within the prediction horizon; guidance uses the IMM prediction-only state.
- `SAFE_HOLD`: measurement age exceeds the horizon; desired velocity becomes zero and the bounded controller decelerates the follower.

Measurement return transitions the supervisor back to `TRACKING` and records reacquisition.

### 5.3 Formal-IMM SIL results

The dedicated GitHub Actions workflow executes fixed-seed deterministic scenarios through the repository's actual formal IMM.

| Scenario | Final standoff error | RMS standoff error after 5 s | Maximum estimator error | Maximum measurement age | Safe-hold time | Reacquisitions |
|---|---:|---:|---:|---:|---:|---:|
| `nominal_visible` | `0.00114 m` | `0.05319 m` | `0.02673 m` | `0.0 s` | `0.0 s` | `0` |
| `short_dropout` | `0.000353 m` | `0.05535 m` | `0.16357 m` | `1.5 s` | `0.0 s` | `1` |
| `long_dropout_safe_hold` | `0.00986 m` | `0.31648 m` | `0.41683 m` | `4.0 s` | `2.0 s` | `1` |

All scenarios produced finite outputs. Maximum commanded acceleration remained bounded by `2.5 m/s²`, and minimum target/follower separation remained above `1.37 m`.

These are synthetic-truth deterministic SIL metrics. They validate software integration and supervisory behavior, not hardware accuracy, PX4, HIL, vehicle dynamics, or flight performance.

## 6. Measurement covariance status

Earlier stationary recordings suggested millimeter-scale raw measurement variation, but they were not collected under the final predeclared protocol. They informed candidate values only.

The controlled protocol is committed at:

```text
docs/CONTROLLED_R_COLLECTION_PROTOCOL.md
```

The hardened collection helper now:

- requires a calibrated camera file and measured camera-to-tag standoff;
- records the protocol commit and repository head;
- reads supported V4L2 controls before setting, after setting, after camera open, and after the trial;
- aborts on supported-control mismatches;
- requires a live `/ghost/vision/target_pose` sample before the 90-second clock;
- records into and resolves the trial recorder's timestamped child directory;
- preserves rejected runs;
- requires a post-trial operator attestation that the physical setup and lighting remained unchanged.

Predeclared numerical collection criteria:

```text
record duration: 90 s
primary analysis window: 15-75 s
minimum fixed-window rate: 10.0 Hz
maximum fixed-window sample gap: 0.25 s
```

The fixed-window analysis reports:

- raw `R_xx`, `R_xy`, and `R_yy`;
- correlation coefficient;
- x/y standard deviations;
- linear drift slopes;
- sample count and sample rate;
- fixed sub-window results over `15–35`, `35–55`, and `55–75 s`;
- relative covariance variation and centroid-offset diagnostics.

Protocol v1 did not predeclare a numerical sub-window stability threshold. Those values are therefore diagnostic and cannot be converted into a post-hoc pass/fail rule.

Required status until physical collection:

```text
R status: CONTROLLED_R_PREDECLARED_PENDING_COLLECTION
Accuracy status: DOES_NOT_VALIDATE_TRACKER_ACCURACY
```

## 7. Physical accuracy-validation status

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

## 8. Paired IMM/MH hardware campaign

The repository contains a predeclared campaign protocol and machine-readable manifest template.

Campaign design:

| Condition | Planned trials |
|---|---:|
| stationary visible repeatability | `5` |
| endpoint, no occlusion | `10` |
| endpoint, 1 s occlusion | `10` |
| endpoint, 2 s occlusion | `10` |
| endpoint, 3 s occlusion | `10` |
| maneuver with predeclared turn and 2 s occlusion | `10` |
| **Total** | **`55`** |

The manifest validator enforces:

- protocol commit format;
- condition and repetition counts;
- unique trial IDs;
- unique condition/repetition slots;
- accepted-trial directories;
- rejected-trial reasons;
- finite endpoint truth;
- complete-campaign status.

The statistical harness reports:

- paired median errors;
- median `MH - IMM` difference;
- median error reduction;
- fixed-seed bootstrap 95% confidence interval;
- Wilcoxon signed-rank result when SciPy is available.

Tests cover a known effect, an all-zero edge case, and a noisy symmetric null effect whose confidence interval must span zero. This validates harness behavior but does not imply a future hardware result.

No tracker-superiority claim is allowed until the real paired trials are accepted and analyzed condition by condition.

## 9. Evidence packaging and public replay

The project includes:

- split IMM and MH futures logs;
- hardware-bag plotting;
- machine-readable JSON export;
- a dependency-free HTML replay dashboard;
- a public GitHub Pages landing page and replay wrapper;
- project, portfolio, GNC, and validation reports;
- downloadable workflow artifacts for deterministic SIL runs.

The replay dashboard presents raw measurements, tracker estimates, IMM mode probabilities, status, measurement age, prediction-only steps, and future tails. It is an integration and telemetry artifact, not an accuracy-validation artifact.

Public site:

```text
https://xpiredruby.github.io/ghost-vins-eskf/
```

## 10. Software engineering and CI

The repository includes:

- ROS 2 Jazzy nodes and launch files;
- portable estimator and legacy guidance components;
- unit tests for covariance, IMM, stationary gating, grid analysis, statistics, demo export, campaign validation, collection quality, and GNC SIL;
- portable C++ build and tests;
- dedicated workflows for general CI, software-regime acceptance, controlled-R pipeline checks, closed-loop GNC SIL, and Pages deployment;
- explicit status strings and claims boundaries;
- split tracker logs so one tracker cannot silently overwrite the other's evidence.

## 11. GNC relevance and limits

GHOST demonstrates:

- hardware sensor measurement handling;
- target state and covariance estimation;
- multiple-model interaction;
- uncertainty propagation;
- stale-measurement supervision;
- deterministic software-only guidance and control;
- command saturation and actuator lag;
- safe hold after prolonged dropout;
- estimator-driven reacquisition.

GHOST does not currently demonstrate:

- PX4 SITL;
- hardware-in-the-loop;
- real actuator identification;
- real vehicle command;
- validated vehicle dynamics;
- flight control or flight test;
- production safety or certification.

## 12. Reproducibility

Build the ROS 2 package:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2 --symlink-install
source install/setup.bash
```

Run the software-only tracker pipeline:

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

Run the deterministic closed-loop GNC SIL:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/closed_loop_gnc_sil.py \
  --out ghost_gnc_sil/manual
```

Run the hardened controlled covariance helper on the Raspberry Pi:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

Serve the static replay locally:

```bash
cd ghost_sim_ros2/docs
python3 -m http.server 8000 --bind 0.0.0.0
```

## 13. Next experimental sequence

1. Execute the hardened controlled covariance trial.
2. Accept or reject it using camera readbacks, timing gates, sample-gap limits, and operator attestation.
3. Keep the camera fixed and execute the measured ground-truth grid.
4. Publish covariance, stability, bias, RMSE, mean error, maximum error, and repeatability.
5. Pin the paired-campaign protocol commit before the first trial.
6. Execute all 55 planned visible and occluded trials.
7. Apply condition-specific paired statistics, reacquisition latency, and failure-rate analysis.
8. Add Raspberry Pi CPU, memory, and thermal evidence.
9. Consider a separately scoped PX4 SITL study only after the estimator evidence is complete.

## 14. Safe conclusion

GHOST provides strong evidence of end-to-end robotics estimation integration: real camera measurements, ROS 2 transport, formal and heuristic trackers, explicit dropout supervision, and reproducible replay tooling. It also provides a real formal-IMM software-in-the-loop guidance-controller-plant chain with bounded control and safe hold.

The project will cross from a hardware-integrated estimator and deterministic GNC SIL demonstration to a quantitatively validated physical system only after the predeclared controlled covariance, ground-truth grid, and paired hardware campaigns are completed.
