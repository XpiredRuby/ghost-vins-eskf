# GHOST-MH Critical Review and Upgrade Roadmap

This document captures the strongest criticism a serious robotics, aerospace, or perception reviewer would make against the current GHOST-MH prototype, and converts each criticism into a concrete upgrade path.

The current system is a successful live prototype: a USB camera observes an AprilTag target, ROS2 publishes calibrated pose, GHOST-MH runs a bounded multi-hypothesis probabilistic tracker, and a browser operator console displays camera evidence, predicted future paths, probabilities, latency indicators, and uncertainty ellipses.

The remaining gap is not whether the demo works. The remaining gap is whether the project is presented and validated like a publishable robotics system.

---

## Executive Criticism

The live prototype is visually impressive, but a reviewer can still dismiss it as a controlled AprilTag demo unless the project adds replay, validation metrics, baseline comparison, ground-truth error analysis, repeatable logs, and clearer limitations.

The correct next iteration is to turn GHOST-MH from a live demo into an evidence-producing experimental platform.

---

## High-Priority Reviewer Criticisms

### 1. The current demo is live-only, not replayable

**Criticism:** A live browser demo is not enough. Reviewers cannot inspect a run after the fact, compare trials, or verify the claim without a replay artifact.

**Fix:** Add mission recording and replay mode.

**Acceptance criteria:**

- Every run creates a timestamped trial folder.
- Trial folder contains camera snapshots or video reference, ROS topic logs, GHOST-MH futures JSON, status timeline, and run metadata.
- Browser dashboard supports `LIVE` and `REPLAY` mode.
- Replay mode includes a scrubber timeline with visible, occluded, predicted, reset, and reacquired events.

**Presentation value:** The project becomes demonstrable even when hardware is unavailable.

---

### 2. There is no side-by-side baseline comparison

**Criticism:** GHOST-MH looks interesting, but the viewer needs to see what it beats. Without a baseline, the contribution is unclear.

**Fix:** Add baseline comparison against constant-velocity Kalman prediction and naive last-seen hold.

**Acceptance criteria:**

- Dashboard has a `Comparison` panel.
- During occlusion it shows:
  - last-seen hold
  - bounded constant velocity tracker
  - GHOST-MH multi-hypothesis tracker
- Reacquisition computes which method was closer.
- Report includes top-1, top-3, and baseline errors.

**Presentation value:** The viewer immediately understands the research contribution: GHOST-MH keeps multiple physically plausible futures instead of pretending a single future is certain.

---

### 3. There is no ground-truth validation protocol yet

**Criticism:** A tracking project without ground-truth error is not scientifically complete.

**Fix:** Add controlled validation trials using a measured grid or printed floor coordinate sheet.

**Acceptance criteria:**

- User can place AprilTag at known grid coordinates.
- System logs measured pose versus known truth.
- Validation script reports bias, RMSE, standard deviation, 95th percentile error, and covariance consistency.
- `measurement_std_m` is tuned from empirical residuals instead of guessed.

**Presentation value:** Converts the claim from “it looks accurate” to “visible pose RMSE is X cm under this setup.”

---

### 4. The phrase “0.00001% error” is physically unrealistic

**Criticism:** Perfect or near-perfect occlusion tracking is impossible with one camera when the target is hidden. During occlusion, there is no new measurement.

**Fix:** Replace absolute accuracy claims with probabilistic claims.

**Correct claim language:**

- Visible target: measured pose error is minimized and quantified.
- Occluded target: GHOST-MH maintains a bounded probability distribution over plausible future states.
- Reacquisition: hypotheses are scored against the returning measurement.
- Failure safety: predictions reset after the validity horizon instead of hallucinating indefinitely.

**Acceptance criteria:**

- README and report never imply perfect hidden-state knowledge.
- Dashboard explicitly labels predictions as probabilistic.
- Evaluation reports coverage probability and error percentiles, not only average error.

---

### 5. The current UI is a custom dashboard, not yet an operator analysis tool

**Criticism:** The dashboard is useful, but it does not yet have the maturity of robotics observability tools: layouts, replay, event markers, synchronized time-series panels, and exportable evidence.

**Fix:** Add operator-grade dashboard modes.

**Acceptance criteria:**

- One-page operator console includes camera, map, probability table, latency, health, and event timeline.
- Optional tabs:
  - `Live`
  - `Replay`
  - `Metrics`
  - `Baseline`
  - `Report`
- Events are marked: `VISIBLE`, `OCCLUSION_START`, `HYPOTHESIS_SPLIT`, `REACQUIRED`, `RESET`.

**Presentation value:** Looks like an actual robotics test console instead of a student visualization script.

---

### 6. The probability paths are lines; they should also be fields

**Criticism:** Lines and percentages are useful, but probability is spatial. A reviewer expects uncertainty regions, covariance, or probability density.

**Fix:** Add heatmap/probability cloud rendering.

**Acceptance criteria:**

- Dashboard renders a probability heatmap over the x-y map.
- Each hypothesis contributes weighted density using its covariance.
- Bright regions represent likely target locations.
- Covariance ellipses remain visible as interpretable summary geometry.

**Presentation value:** Communicates that GHOST-MH is not guessing one hidden trajectory; it maintains a spatial belief field.

---

### 7. Latency is visible but not yet decomposed

**Criticism:** The system shows browser/payload age, but not the full timing chain. A robotics reviewer will ask where the delay comes from.

**Fix:** Add latency pipeline instrumentation.

**Acceptance criteria:**

- Report estimates or measures:
  - camera frame interval
  - AprilTag detection time
  - ROS publish delay
  - GHOST-MH update time
  - dashboard polling/render time
  - total sensor-to-screen latency
- Dashboard shows a latency waterfall or timing table.
- ROS2 tracing is listed as the next rigorous implementation path.

**Presentation value:** Turns “it feels 0.5 seconds slow” into an engineering problem with measurable bottlenecks.

---

### 8. AprilTag-only tracking looks lab-constrained

**Criticism:** AprilTag tracking is excellent for controlled validation, but it can look less impressive than object-level tracking because the target carries an artificial marker.

**Fix:** Keep AprilTag mode as the calibrated measurement benchmark, then add tagless mode later.

**Acceptance criteria:**

- Dashboard mode selector:
  - `AprilTag calibrated mode`
  - `Tagless detector mode` future work
- Tagless mode uses detector + tracker association later.
- AprilTag remains the trusted source for controlled validation and error calibration.

**Presentation value:** Shows the project has a rigorous lab mode and a path toward real-world markerless perception.

---

### 9. Single-camera setup limits observability

**Criticism:** A single monocular camera observing a planar AprilTag is limited by calibration quality, occlusion geometry, frame rate, lighting, and target visibility.

**Fix:** Present single-camera as version 1 and define sensor-fusion upgrades.

**Acceptance criteria:**

- Roadmap includes:
  - second camera / stereo mode
  - IMU-assisted camera motion compensation
  - depth camera option
  - tagless object detector
  - optional UWB/ground-truth anchor for validation

**Presentation value:** Shows that GHOST-MH is an architecture, not a one-off webcam script.

---

### 10. The motion priors need empirical calibration

**Criticism:** The mode probabilities depend on priors and process models. If those are hand-selected, a reviewer can challenge the physics credibility.

**Fix:** Learn or calibrate mode priors from logged trial data.

**Acceptance criteria:**

- Trial logs are used to estimate:
  - typical velocity range
  - acceleration range
  - lateral motion frequency
  - braking/hover probability
  - turn model likelihood
- Mode weights can be exported and versioned.
- Dashboard displays the active mode bank configuration.

**Presentation value:** Turns hand-tuned probabilities into data-calibrated priors.

---

### 11. There is no formal failure-mode analysis yet

**Criticism:** A strong system should show where it fails, not only where it succeeds.

**Fix:** Add a failure-mode table and scenario suite.

**Acceptance criteria:**

- Scenarios include:
  - slow target
  - fast target
  - sudden stop
  - lateral motion
  - partial occlusion
  - full occlusion
  - target exits workspace
  - false detection rejection
  - long hidden interval reset
- Each scenario gets pass/fail metrics.

**Presentation value:** Makes the project credible because it admits and bounds limitations.

---

### 12. There is no automatic report export

**Criticism:** A demo without an exported report is hard to grade, share, or review later.

**Fix:** Add `Export Report`.

**Acceptance criteria:**

- After each trial, generate a Markdown or PDF report containing:
  - trial metadata
  - event timeline
  - metrics table
  - baseline comparison
  - selected screenshots
  - interpretation paragraph
  - limitations
- Reports are saved under `~/ghost_logs/reports/`.

**Presentation value:** User can send a professional artifact to engineers, recruiters, professors, or reviewers.

---

## Proposed Implementation Phases

### Phase 1 — Presentation Credibility

Goal: make the existing prototype look and feel like a serious research demo.

Tasks:

1. Add event timeline to dashboard.
2. Add run recording into timestamped trial folders.
3. Add replay mode from recorded JSON.
4. Add baseline comparison overlay.
5. Add automatic trial summary metrics.

Expected outcome: GHOST-MH becomes easy to present and defend.

---

### Phase 2 — Validation Credibility

Goal: quantify accuracy instead of relying on visual judgment.

Tasks:

1. Build grid/ruler calibration protocol.
2. Add static-pose validation script.
3. Add dynamic occlusion validation script.
4. Tune `measurement_std_m` from data.
5. Report visible RMSE, occlusion prediction error, top-1 accuracy, top-3 coverage, and reset correctness.

Expected outcome: GHOST-MH produces real numbers suitable for a technical report.

---

### Phase 3 — Research Differentiation

Goal: make the contribution distinct from a basic Kalman tracker.

Tasks:

1. Add probability heatmap.
2. Add mode-prior calibration from logs.
3. Add baseline-versus-GHOST plots.
4. Add failure-mode suite.
5. Add latency profiler.

Expected outcome: GHOST-MH can be described as a bounded multi-hypothesis occlusion tracker with evidence-backed uncertainty.

---

### Phase 4 — Advanced Expansion

Goal: expand beyond AprilTags.

Tasks:

1. Add tagless detector input mode.
2. Add 3D camera-frustum visualization.
3. Add stereo/depth support.
4. Add visual-inertial camera-platform compensation.
5. Add optional Foxglove/ROS bag/MCAP export path.

Expected outcome: GHOST becomes an extensible robotics perception platform rather than a fixed demo.

---

## Recommended Dashboard End State

One browser operator console should contain:

- live camera evidence
- top-down probability map
- heatmap belief field
- covariance ellipses
- ranked hypothesis table
- baseline comparison panel
- event timeline
- latency waterfall
- metrics tab
- replay controls
- export report button

---

## Recommended Metrics

Visible target metrics:

- position bias in x and y
- RMSE position error
- standard deviation of residuals
- 95th percentile error
- covariance consistency
- latency from measurement to dashboard

Occlusion metrics:

- top-1 hypothesis final error
- top-3 coverage at reacquisition
- best-hypothesis error
- mean error versus occlusion duration
- reset correctness after max horizon
- false-confidence rate

Presentation metrics:

- recorded runs count
- exportable report count
- reproducible demo command
- dashboard uptime
- CPU load and frame rate

---

## Language to Use in Presentations

Use this:

> GHOST-MH is a real-time ROS2 multi-hypothesis tracker that maintains a bounded probability distribution over physically plausible target futures during visual occlusion. It does not hallucinate certainty. It predicts, scores, and resets based on measurement availability, covariance, and calibrated motion priors.

Avoid this:

> It knows where the target is while hidden.

Use this:

> During occlusion, GHOST-MH reports top-1 and top-3 belief futures with uncertainty. When the target reappears, it measures whether the correct future was covered.

Avoid this:

> It has near-zero hidden-target error.

---

## Source-Inspired Design Notes

- Robotics visualization tools emphasize recording, organizing, visualizing, replaying, and sharing multimodal robot data such as time series, video, 3D data, maps, panels, layouts, recordings, metadata, and events. GHOST should copy that workflow pattern instead of only showing a live demo.
  - https://docs.foxglove.dev/docs

- Tracking benchmarks and metrics matter because live visual impressions can be misleading. MOTChallenge and HOTA motivate reporting localization, detection/association quality, coverage, and error categories rather than only showing trajectories.
  - https://arxiv.org/abs/2010.07548
  - https://arxiv.org/abs/2009.07736

- ROS2 runtime performance should be measured with instrumentation rather than guessed. `ros2_tracing` is a strong reference for low-overhead tracing and latency analysis.
  - https://arxiv.org/abs/2201.00393

- Visual-inertial and SLAM systems show how mature robotics projects handle sensor fusion, initialization, relocalization, and map reuse. These are not required for GHOST-MH v1, but they define the direction for later versions.
  - https://arxiv.org/abs/1708.03852
  - https://arxiv.org/abs/2007.11898

- Tagless tracking can be added later using detector-plus-association methods. ByteTrack is a relevant example because it argues that low-confidence detections during occlusion can still help recover true objects.
  - https://arxiv.org/abs/2110.06864

---

## Immediate Next Build Recommendation

The next implementation should be:

1. Record run data to `~/ghost_logs/trials/<timestamp>/`.
2. Add event timeline to the browser dashboard.
3. Add baseline comparison: last-seen hold, constant velocity, GHOST-MH.
4. Add replay mode from saved trial JSON.
5. Add automatic Markdown report export.

This is the fastest path from working prototype to presentation-grade research demo.
