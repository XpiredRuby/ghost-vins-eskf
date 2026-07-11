# GHOST Project Report

_Last synchronized after the USB hardware/BOM, campaign operations, audited analysis, evidence integrity, runtime/timing, physical-session, parameter-lock, and release-claims tooling were merged._

## 1. Executive summary

GHOST is a Raspberry Pi and ROS 2 target-estimation project for intermittent AprilTag visibility. The active camera backend is a **standard USB UVC webcam through Linux V4L2**, not a CSI camera. The live hardware pipeline runs two trackers from the same measurement stream:

1. a formal Interacting Multiple Model (IMM) estimator; and
2. a bounded heuristic multi-hypothesis tracker, GHOST-MH, used as an operational comparison baseline.

The preserved hardware run demonstrates live USB-camera measurement ingestion, simultaneous tracker output near 30 Hz, explicit prediction-only behavior during target loss, degraded-dropout status, and recovery after measurements return.

The repository also contains a deterministic software-in-the-loop GNC harness that connects the same formal IMM to relative-standoff guidance, an acceleration-limited velocity controller, first-order actuator lag, follower dynamics, and a three-state `TRACKING` / `PREDICTION` / `SAFE_HOLD` supervisor.

All meaningful hardware-free preparation for the next physical phase is implemented: privacy-safe USB hardware inventory, machine-readable BOM, hardened controlled covariance collection, fixed-window/sub-window analysis, measured-grid accuracy analysis and visuals, a 55-slot paired IMM/MH campaign, balanced randomization, local trial conductor, immutable plan/audited outcome state, condition-specific statistics, runtime/timing instrumentation, SHA-256 evidence packaging, formal parameter locking, a public claims gate, a dependency-gated session checklist, and a three-take hero demonstration protocol.

**Evidence boundary:** current hardware evidence validates integration, publication timing, telemetry, dropout-state behavior, and replay. Current GNC evidence validates deterministic software-only estimator-guidance-controller-plant integration. Neither establishes physical tracking accuracy, hardware controller performance, PX4/HIL integration, vehicle command, production readiness, flight readiness, or flight testing.

## 2. Engineering problem

A vision detector produces observations only while a target can be detected. During occlusion, blur, lighting degradation, or dropped frames, a useful tracking and autonomy stack must:

- propagate state without pretending that a measurement exists;
- represent increasing uncertainty;
- expose the age of the last valid observation;
- constrain the duration and interpretation of open-loop prediction;
- transition to safe behavior when prediction becomes too stale;
- recover when measurements return;
- preserve enough telemetry and configuration evidence to audit the behavior afterward.

GHOST treats dropout as an estimator and supervisor state rather than hiding it behind a smooth trajectory plot.

## 3. Hardware estimation architecture

```text
AprilTag target
        |
        v optical image
USB UVC webcam
        |
        v USB + V4L2/UVC
Raspberry Pi / ROS 2 Jazzy
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

### 3.1 USB camera backend

The validated baseline is a conventional USB UVC webcam. Linux V4L2 provides the device modes and controls. Exact manufacturer/model, vendor/product ID, active mode, cable details, power supply, mount construction, and replacement cost remain pending the physical inventory session.

Unless independent hardware timestamp support is proven, USB camera timing is treated as software/arrival timing rather than shutter-open timing.

### 3.2 Vision measurement

The AprilTag publisher provides a timestamped two-dimensional target position through:

```text
/ghost/vision/target_pose
```

The live covariance path supports a full symmetric measurement matrix:

```text
R = [[R_xx, R_xy],
     [R_xy, R_yy]]
```

Telemetry confirms that both trackers receive and report the expected full-`R` metadata. This verifies plumbing—not the correctness of candidate covariance values.

### 3.3 Formal IMM tracker

The IMM maintains multiple motion-model filters, mixes states and covariances, updates mode probabilities from measurement likelihoods, and combines model-conditioned outputs into one estimate.

Live outputs:

```text
/ghost/tracker_imm/target_odom
/ghost/tracker_imm/futures_json
/ghost/tracker_imm/status
```

The live configuration distinguishes smooth constant-velocity behavior from a higher-process-noise maneuver model. Its mode values are valid IMM probabilities.

### 3.4 GHOST-MH tracker

The heuristic GHOST-MH tracker provides bounded candidate futures and operational context during temporary target loss.

Live outputs:

```text
/ghost/tracker_mh/target_odom
/ghost/tracker_mh/futures_json
/ghost/tracker_mh/status
```

Its rankings are **relative hypothesis weights**, not calibrated probabilities. It is not presented as a replacement for a formal Bayesian estimator.

## 4. Preserved hardware integration evidence

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

The run verifies that the USB webcam measurement source and both trackers operated together in real time and emitted reviewable state, status, and future-path telemetry. During target loss, the IMM entered prediction-only and dropout-degraded states before returning to tracking after reacquisition.

The run does not contain independent physical ground truth and therefore does not establish tracking RMSE or tracker superiority.

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

Guidance:

```text
r      = p_target_est - p_follower
e_r    = ||r|| - r_standoff
v_des  = v_target_est + sat(k_r * e_r) * r / ||r||
```

Control:

```text
a_cmd = sat(k_v * (v_des - v_follower))
```

The actuator is modeled as a first-order response before follower dynamics integrate achieved acceleration.

### 5.2 Supervisor

- `TRACKING`: a measurement is available; guidance uses the measurement-updated IMM estimate.
- `PREDICTION`: measurement is absent but age is within the prediction horizon; guidance uses the IMM prediction-only state.
- `SAFE_HOLD`: measurement age exceeds the horizon; desired velocity becomes zero and the bounded controller decelerates the follower.

Measurement return transitions the supervisor back to `TRACKING` and records reacquisition.

### 5.3 Deterministic results

| Scenario | Final standoff error | RMS standoff error after 5 s | Maximum estimator error | Maximum measurement age | Safe-hold time | Reacquisitions |
|---|---:|---:|---:|---:|---:|---:|
| `nominal_visible` | `0.00114 m` | `0.05319 m` | `0.02673 m` | `0.0 s` | `0.0 s` | `0` |
| `short_dropout` | `0.000353 m` | `0.05535 m` | `0.16357 m` | `1.5 s` | `0.0 s` | `1` |
| `long_dropout_safe_hold` | `0.00986 m` | `0.31648 m` | `0.41683 m` | `4.0 s` | `2.0 s` | `1` |

All scenarios produced finite outputs. Maximum commanded acceleration remained bounded by `2.5 m/s²`, and minimum target/follower separation remained above `1.37 m`.

These are synthetic-truth deterministic SIL metrics. They validate software integration and supervisory behavior—not hardware accuracy, PX4, HIL, vehicle dynamics, or flight performance.

## 6. USB hardware and BOM preparation

The repository now contains:

- a machine-readable `hardware_bom.json`;
- a public hardware/BOM page;
- an interface-control table;
- explicit verification status for every component;
- a ten-photo evidence checklist;
- privacy rules for serial numbers, network data, unique identifiers, screens, and personal information;
- a privacy-separated inventory tool that captures `lsusb`, V4L2 devices, modes, controls, udev properties, Pi model, and calibration hash into private and reviewable-public trees.

Exact hardware fields remain intentionally pending until the physical setup is available. This prevents the public portfolio from inventing a webcam model, Pi revision, cost, or mount specification.

## 7. Controlled measurement covariance

Earlier stationary recordings suggested millimeter-scale raw measurement variation, but they were not collected under the final predeclared protocol and informed candidate values only.

The hardened workflow:

- requires a calibrated camera file and measured standoff;
- records protocol commit and repository head;
- reads supported V4L2 controls before setting, after setting, after camera open, and after the trial;
- aborts on supported-control mismatches;
- requires a live `/ghost/vision/target_pose` sample before the 90-second clock;
- resolves the trial recorder's timestamped child directory;
- preserves rejected runs;
- requires a post-trial physical-integrity attestation.

Predeclared criteria:

```text
record duration: 90 s
primary analysis window: 15-75 s
minimum fixed-window rate: 10.0 Hz
maximum fixed-window sample gap: 0.25 s
```

The fixed-window analysis reports raw `R_xx`, `R_xy`, `R_yy`, correlation, standard deviations, drift slopes, sample count/rate, and fixed `15–35`, `35–55`, and `55–75 s` diagnostics.

Protocol v1 did not predeclare a numerical sub-window stability threshold. Those values remain diagnostic and cannot be converted into a post-hoc pass/fail rule.

Required status until physical collection:

```text
R status: CONTROLLED_R_PREDECLARED_PENDING_COLLECTION
Accuracy status: DOES_NOT_VALIDATE_TRACKER_ACCURACY
```

## 8. Physical ground-truth grid

The physical protocol requires six measured non-collinear points, variation in both axes, the same locked camera setup as controlled covariance, and at least 10 seconds stationary per point.

Implemented outputs:

- per-point measured means and standard deviations;
- `dx` and `dy` bias;
- Euclidean point error;
- aggregate bias;
- RMSE, mean error, and maximum error;
- sample count and sample rate;
- truth-versus-measured plot;
- error vectors;
- per-point error plot;
- discrete spatial error map;
- static grid dashboard.

The spatial map intentionally does not interpolate a continuous accuracy surface from only six points.

No grid results are reported because the physical trial has not yet been run.

## 9. Paired IMM/MH hardware campaign

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

### 9.1 Campaign initialization

The initializer:

- pins the committed protocol revision;
- expands all 55 planned slots;
- generates balanced deterministic randomization;
- creates every trial directory;
- creates per-trial conductor and metadata files;
- validates the manifest;
- hashes the manifest, order, and validation output into a campaign lock;
- refuses to overwrite a non-empty campaign directory.

### 9.2 Local conductor

A browser-based local conductor provides large visual cues, speech/audio, high-resolution timing, pause/resume, required rejection reasons, downloadable local logs, and server-side conductor event JSONL.

The conductor assists choreography. Actual acceptance remains based on the measured vision gap, not browser timing alone.

### 9.3 Immutable plan and audited outcomes

The precollection `campaign_manifest.json`, `randomized_trial_order.csv`, and lock remain immutable. Outcomes live separately in:

```text
campaign_state.json
campaign_amendments.jsonl
campaign_manifest_effective.json
campaign_validation_current.json
```

Accepted occlusion trials require finite endpoint truth, actual gap within ±0.25 seconds, and exactly one usable vision/IMM/MH log. Rejections require reasons and remain preserved. Changing an already recorded outcome requires an explicit amendment reason. Finalization is blocked while any slot remains planned.

## 10. Campaign analysis and public visuals

The audited analysis pipeline derives:

- measured inter-sample vision gap and supplementary estimated missing duration;
- endpoint prediction error;
- first-reacquisition error;
- reacquisition latency;
- maximum measurement age and covariance trace;
- reset/failure state;
- relative trajectory series;
- condition-specific paired medians;
- median `MH - IMM` difference;
- fixed-seed bootstrap 95% confidence intervals;
- Wilcoxon signed-rank reporting when SciPy is available;
- gap-tolerance, failure, and report-grade/exploratory counts.

Unlike occlusion durations are never pooled into one significance claim. Accepted trials that fail the raw-log gap check remain visible in quality counts but are excluded from report-grade paired statistics.

Public plots include paired physical-trial lines, explicitly labeled error distributions, error versus actual gap, reacquisition latency, failures, trajectory overlays, and one mechanically selected median-like representative run per condition. Representative runs are not selected by appearance or minimum error.

The campaign uses physically measured stationary endpoint truth. It does not provide independent time-synchronized full dynamic trajectory truth; therefore the project does not claim full-path dynamic RMSE.

## 11. USB timing and Raspberry Pi runtime characterization

Prepared USB timing outputs include:

- effective camera-pose rate;
- interarrival median/mean/std/min/p05/p95/max;
- median absolute jitter;
- long-interval/drop proxies;
- estimated missed-frame-interval proxy;
- ROS receive-minus-header-stamp diagnostics;
- negative-latency clock diagnostic.

Prepared Pi resource outputs include:

- system CPU and one-minute load;
- system used/available memory;
- thermal-zone temperature;
- matching GHOST/AprilTag/ROS process count;
- aggregate matching-process CPU and RSS;
- median, mean, 95th percentile, and maximum summaries.

These will characterize the recorded USB/Pi session. They will not establish worst-case qualification, hardware timestamp accuracy, thermal certification, or flight-computer suitability.

## 12. Evidence integrity and configuration control

### 12.1 Evidence packaging

Profile-aware evidence packaging creates non-overwriting ZIP archives containing:

```text
EVIDENCE_MANIFEST.json
EVIDENCE_MANIFEST.sha256
evidence/<original relative files>
```

The verifier checks manifest hash, every listed file hash/size, missing members, unexpected members, ZIP readability, and JSON validity. Focused tests deliberately tamper with an archive member and require detection.

SHA-256 detects post-package byte changes. It does not prove physical validity or correct scientific interpretation.

### 12.2 Parameter lock

Before formal collection, the project can lock:

- Git HEAD/branch/status;
- formal IMM/MH implementations;
- estimator core files;
- protocols and manifest template;
- camera calibration;
- camera-control snapshot;
- ROS runtime-parameter snapshot.

A hash mismatch or Git revision change fails verification. Any configuration change creates a new configuration block and blocks casual pooling.

### 12.3 Public claims gate

The machine-readable release matrix classifies statements as:

- `validated`;
- `hardware_behavior_only`;
- `software_only`;
- `pending`;
- `prohibited`.

The validator blocks public-ready pending/prohibited claims, placeholders, missing evidence/limitations, high-risk wording without validated classification, accuracy language in behavior-only claims, and unresolved pending claims in a final release matrix.

## 13. Physical-session and hero-demonstration control

An 11-phase machine-readable checklist covers:

1. hardware inventory;
2. rigid setup lock;
3. controlled covariance;
4. ground-truth grid;
5. campaign dry runs;
6. parameter lock;
7. formal campaign;
8. runtime characterization;
9. hero demonstration;
10. analysis and integrity;
11. public release review.

The validator blocks a phase from passing before dependencies and can require declared artifacts.

The hero demonstration is separate from the statistical campaign. Exactly three takes are preserved. Eligibility prioritizes valid gaps, complete logs, physical/control integrity, broad 2D coverage, and few unintended detection losses. Selection is for explanatory clarity—not lowest endpoint error.

## 14. Public presentation

The project includes:

- one-click GitHub Pages landing page;
- interactive preserved-hardware replay;
- public USB hardware/BOM page;
- hardware plots and status timelines;
- portfolio and technical reports;
- GNC SIL reports and workflow artifacts;
- validation, operations, analysis, integrity, and claims documentation.

Public site:

```text
https://xpiredruby.github.io/ghost-vins-eskf/
```

## 15. Software engineering and CI

The repository includes:

- ROS 2 Jazzy nodes and launch files;
- portable estimator and legacy guidance components;
- Python and portable C++ tests;
- dedicated workflows for general CI, software-regime acceptance, controlled-R, GNC SIL, campaign operations, campaign analysis, evidence integrity, hardware BOM/privacy, timing/runtime, physical-session readiness, parameter/claims locks, and Pages deployment;
- explicit status strings and claims boundaries;
- split tracker logs so one tracker cannot overwrite the other's evidence.

All new hardware-free preparation tools include focused tests and passed their dedicated and broad workflows before merge.

## 16. Reproducibility entry points

Build:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2 --symlink-install
source install/setup.bash
```

Run deterministic GNC SIL:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/closed_loop_gnc_sil.py \
  --out ghost_gnc_sil/manual
```

Run controlled covariance on the Pi:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

Initialize formal campaign:

```bash
python3 ghost_sim_ros2/tools/campaign_operations.py \
  --template ghost_sim_ros2/docs/IMM_MH_CAMPAIGN_MANIFEST.example.json \
  --out ~/ghost_trials/imm_mh_campaign_v1 \
  --resolve-protocol-commit \
  --repo-root .
```

Run audited analysis:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/campaign_analysis_runner.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --out-dir ~/ghost_trials/imm_mh_campaign_v1/analysis
```

## 17. Next physical sequence

1. Capture privacy-separated exact USB/Pi inventory and photographs.
2. Rigidly mount the USB webcam and AprilTag; define axes, standoff, grid, path, and occluder.
3. Execute the hardened controlled covariance trial and require its saved quality gate to pass.
4. Keep the same setup and execute the six-point grid.
5. Perform one dry run for each campaign condition.
6. Lock estimator, calibration, controls, protocols, and runtime parameters.
7. Initialize and freeze the balanced randomized 55-slot campaign.
8. Execute every slot using local cues and audited accept/reject state.
9. Collect representative Pi runtime and USB timing evidence.
10. Preserve three hero demonstration takes.
11. Finalize state, analyze, generate plots, package, verify, copy, and reverify.
12. Promote only claims that pass the release matrix.

## 18. Safe conclusion

GHOST provides strong evidence of end-to-end robotics estimation integration: real USB-webcam measurements, Raspberry Pi/ROS 2 transport, formal and heuristic trackers, explicit dropout supervision, and reproducible public replay. It also provides a real formal-IMM software-in-the-loop guidance-controller-plant chain with bounded control and safe hold.

The software, methodology, operations, analysis, integrity, and presentation preparation needed for rigorous physical validation is now complete. The remaining score gap is evidence-limited rather than software-limited.

GHOST will cross from a hardware-integrated estimator and deterministic GNC SIL demonstration to a quantitatively validated physical system only after the controlled covariance, measured grid, repeated paired campaign, runtime characterization, and physical documentation are executed and reviewed.
