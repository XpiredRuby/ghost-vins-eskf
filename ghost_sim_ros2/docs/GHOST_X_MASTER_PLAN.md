# GHOST-X
## Hardware-Validated Autonomous Navigation, Tracking, and Sensor-Fusion Research Platform

**Full-depth ceiling:** 97/100  
**Estimated remaining effort:** 350–550 focused hours  
**No-purchase path:** Existing Raspberry Pi/camera, ROS bags, public benchmarks, software simulation  
**Primary roles:** Navigation, GNC, autonomy, robotics software, estimation, modeling/simulation, integration/test

---

## 1. Engineering mission

Determine how reliably a resource-constrained autonomous system can estimate and predict target motion through:

- visibility loss;
- changing target dynamics;
- measurement latency;
- false and out-of-sequence measurements;
- calibration uncertainty;
- compute overload;
- sensor degradation;
- estimator mismatch.

The final platform shall compare multiple estimation architectures using identical inputs and truth.

---

## 2. Final system

### Required estimators
1. Formal interacting multiple-model estimator.
2. GHOST multi-hypothesis tracker.
3. Constant-velocity or Kalman baseline.
4. Optional factor-graph or smoothing implementation for offline truth-quality comparison.

### Required execution modes
- Live Raspberry Pi camera
- Saved ROS bag replay
- Pure simulation
- Fault-injection replay
- Batch Monte Carlo
- Real-time target execution

### Required outputs
- State estimate and covariance
- Mode/hypothesis probabilities
- Future trajectories
- Validity/status
- Measurement age and latency
- Resource usage
- Fault and recovery events
- Machine-readable trial metrics

---

## 3. No-purchase validation plan

Use:

- the existing Raspberry Pi and camera;
- printed AprilTags using normal university printing access;
- marked room geometry or existing floor/grid references;
- deterministic synthetic truth;
- public AprilTag or vision datasets where useful;
- public motion-capture or robotics datasets;
- a second offline estimator implementation;
- campus motion-capture or robotics facilities only if access is free.

The project shall not depend on buying an IMU, rail, lidar, or metrology system.

---

## 4. Step-by-step execution

### Phase G0 — Freeze current evidence
1. Tag the current main branch.
2. Preserve calibrated live bags.
3. Generate a complete baseline manifest:
   - hardware;
   - operating system;
   - ROS version;
   - camera configuration;
   - calibration;
   - parameters;
   - commit;
   - topic rates.
4. Regenerate all existing plots from one command.
5. Document every unsupported or provisional claim.

**Exit:** Existing results are reproducible from a clean checkout.

### Phase G1 — Requirements and V&V architecture
1. Write system, estimator, timing, and evidence requirements.
2. Define success metrics:
   - position/velocity RMSE;
   - NIS/NEES where valid;
   - reacquisition time;
   - false-track rate;
   - dropout growth;
   - processing latency;
   - publication jitter;
   - CPU/memory.
3. Define nominal and failure scenarios before collecting new data.
4. Create requirements-to-test traceability.
5. Hold an SRR-style review.

**Exit:** Every future public claim maps to a test.

### Phase G2 — Frames, timing, and data contracts
1. Define all frames and transformations.
2. Define timestamp origin and synchronization.
3. Define units and covariance conventions.
4. Define message validity and stale-data behavior.
5. Add schema validation to JSON/status outputs.
6. Add recorded calibration identifiers to every bag.

**Exit:** No ambiguous frame, time, unit, or validity interpretation remains.

### Phase G3 — Measurement characterization
1. Collect stationary datasets at multiple ranges and orientations.
2. Estimate bias, variance, cross-correlation, drift, and autocorrelation.
3. Check whether residuals are white and Gaussian.
4. Separate measurement noise from calibration and ground-truth error.
5. Implement constant and state-dependent covariance alternatives.
6. Predeclare model selection criteria.

**Exit:** Measurement covariance is data-derived and limitations are explicit.

### Phase G4 — Controlled truth campaign
Create at least these trajectories:
- stationary;
- constant velocity;
- acceleration/deceleration;
- coordinated turn or arc;
- stop-and-go;
- abrupt maneuver;
- partial and complete occlusion;
- repeated re-entry.

For each trajectory:
1. Define truth-generation method.
2. Define ground-truth uncertainty.
3. Define operator procedure.
4. Record at least 20 paired trials across the campaign.
5. Randomize estimator labels in analysis where practical.
6. Retain failed and invalid trials with reasons.

**Exit:** Both estimators receive identical measurements and truth.

### Phase G5 — Modern C++ estimator library
1. Separate dynamics, measurements, mode mixing, likelihoods, and ROS adapters.
2. Use Eigen and clear ownership.
3. Implement deterministic configuration loading.
4. Add unit tests for every mathematical component.
5. Add property tests for covariance symmetry/positive semidefiniteness.
6. Add sanitizers and static analysis.
7. Compare C++ output with Python reference vectors.

**Exit:** C++/Python equivalence meets declared tolerances.

### Phase G6 — Formal consistency analysis
1. Compute innovations.
2. Compute NIS.
3. Compute NEES only where truth covariance is defensible.
4. Report confidence bounds and violations.
5. Examine colored residuals and non-Gaussian behavior.
6. Compare nominal and adaptive covariance models.
7. State when consistency tests are invalid.

**Exit:** Covariance claims are mathematically and empirically qualified.

### Phase G7 — Multi-model and hypothesis study
Sweep:
- transition probabilities;
- process noise;
- model count;
- hypothesis pruning;
- future horizon;
- stationary prior;
- dropout thresholds.

Evaluate:
- accuracy;
- false confidence;
- compute cost;
- recovery;
- probability calibration;
- failure regimes.

**Exit:** Final parameters are chosen through a predeclared trade study.

### Phase G8 — Fault injection
Inject:
- camera disconnect;
- frozen measurement;
- duplicate measurement;
- false detection;
- covariance corruption;
- latency;
- out-of-sequence data;
- node restart;
- CPU saturation;
- network degradation;
- parameter mismatch;
- lighting degradation.

For each fault:
1. Detection.
2. Isolation.
3. Status.
4. Recovery.
5. Evidence.
6. Discrepancy.

**Exit:** Fault behavior is reproducible and requirements-based.

### Phase G9 — DDS and real-time behavior
1. Compare reliable and best-effort QoS.
2. Test deadline, liveliness, history, and queue depth.
3. Measure end-to-end latency.
4. Measure estimator execution time and jitter.
5. Measure CPU, memory, and thermal throttling.
6. Stress the Pi with background load.
7. Report worst-case rather than average-only timing.

**Exit:** “Real-time” is supported by deadline evidence or is not claimed.

### Phase G10 — Deterministic replay and CI
1. Package canonical bags and synthetic scenarios.
2. Pin configurations and seeds.
3. Add one-command replay.
4. Compute metrics automatically.
5. Compare to stored acceptance bands.
6. Fail CI on regressions.
7. Generate report tables automatically.

**Exit:** A code change cannot silently degrade canonical scenarios.

### Phase G11 — Optional advanced estimation
Choose one:
- factor graph with GTSAM;
- fixed-lag smoother;
- learned maneuver classifier feeding IMM transitions;
- residual model with confidence-gated fallback;
- asynchronous camera and simulated RF/range fusion.

Requirements:
- classical baseline remains available;
- frozen evaluation set;
- ablation study;
- latency and compute report;
- out-of-distribution tests.

### Phase G12 — Final research package
Produce:
- system requirements;
- estimator derivation;
- measurement report;
- ground-truth protocol;
- trial manifest;
- statistical report;
- timing/resource report;
- fault report;
- software verification report;
- reproducible release;
- 90-second public demo;
- 10-minute technical defense;
- approved résumé claims.

---

## 5. Mandatory acceptance criteria

- Real hardware evidence
- Controlled truth campaign
- At least 20 paired trials
- Identical inputs for estimator comparison
- C++ production implementation
- Independent Python reference
- Statistical uncertainty
- Consistency analysis with validity conditions
- At least 10 injected faults
- Deterministic replay
- CI regression
- CPU, memory, latency, jitter, and thermal evidence
- Requirements traceability
- Public failure gallery
- External review or benchmark

---

## 6. Rating conditions

- **90 or below:** live demo and plots without controlled truth
- **93:** controlled trials but weak software assurance
- **95:** strong hardware campaign, C++ tests, replay, and quantified comparison
- **97:** all full-depth criteria, formal consistency discipline, faults, and real-time evidence
- **98+:** publication, external lab benchmark, or richer no-cost sensor/testbed access

---

## 7. Final portfolio evidence

Recommended public claim after completion:

> Built and hardware-validated a ROS 2 autonomous tracking platform comparing formal IMM and multi-hypothesis estimation across controlled maneuvers, occlusions, false measurements, timing faults, and compute stress; quantified accuracy, covariance consistency, reacquisition, latency, and resource use through deterministic replay and paired trials.
