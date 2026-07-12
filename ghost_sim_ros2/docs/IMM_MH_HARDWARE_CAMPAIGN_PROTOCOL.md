# GHOST IMM/MH Hardware Comparison Campaign — Protocol v1

## Purpose

Collect paired hardware trials that allow the formal IMM and heuristic GHOST-MH trackers to be compared under the same AprilTag measurement stream.

This protocol is committed before campaign data are collected. It is designed to measure endpoint prediction and reacquisition behavior with physically measured stationary endpoints. It does not claim full dynamic trajectory truth or flight readiness.

## Claims boundary

The campaign may support condition-specific statements about:

- endpoint prediction error;
- reacquisition error;
- reacquisition latency;
- reset/failure rate;
- error growth versus measurement-gap duration;
- paired IMM/MH differences with confidence intervals.

It may not support claims about:

- full-path dynamic RMSE unless an independent time-synchronized trajectory truth source is added;
- production robustness;
- general object tracking;
- autonomous guidance/control;
- flight performance.

No tracker-superiority statement is allowed until the predeclared paired analysis is executed on accepted trials.

## Prerequisites

Before campaign collection:

1. Complete the controlled stationary covariance trial.
2. Complete the measured ground-truth grid trial.
3. Keep the same rigid camera mounting and locked camera controls where practical.
4. Record the protocol commit in the campaign manifest.
5. Replace the `0000000` placeholder in the example manifest with that commit and change `protocol_commit_status` to `PINNED_BEFORE_COLLECTION`.
6. Generate and save the randomized trial order before observing campaign results.

## Campaign conditions

The example manifest predeclares six conditions.

| Condition | Repetitions | Target gap | Ground truth |
|---|---:|---:|---|
| `static_visible` | 5 | `0 s` | measured stationary point |
| `endpoint_no_occlusion` | 10 | `0 s` | measured stationary endpoint |
| `endpoint_occ_1s` | 10 | `1 s` | measured stationary endpoint |
| `endpoint_occ_2s` | 10 | `2 s` | measured stationary endpoint |
| `endpoint_occ_3s` | 10 | `3 s` | measured stationary endpoint |
| `maneuver_occ_2s` | 10 | `2 s` | measured stationary endpoint after one predeclared turn |

Total planned trials: **55**.

The minimum for a report-grade condition-specific paired summary is **8 accepted trials per 10-trial condition**. Conditions below that threshold must be labeled exploratory. The five-trial stationary condition is a repeatability diagnostic and is not used to claim tracker superiority.

## Physical geometry

- Use measured start and endpoint marks in meters.
- Photograph or diagram the coordinate origin, axes, path, occluder, and endpoint.
- Do not move the camera during a condition block.
- Use the controlled camera settings established for the stationary covariance trial.
- Keep the AprilTag rigidly attached to its target carrier.
- Do not use hand-held camera motion.
- Record endpoint truth as `endpoint_truth_m.x` and `endpoint_truth_m.y` in the manifest.

## Trial sequence

Each endpoint trial uses the same structure:

1. **Pre-roll:** target visible and stationary at the measured start for at least `3 s`.
2. **Motion:** move the target along the predeclared path.
3. **Occlusion:** block the tag for the condition's target duration.
4. **Endpoint:** place the target on the measured endpoint and stop before or at reveal.
5. **Reveal and hold:** reveal the tag and keep the target stationary for at least `5 s`.
6. **Post-roll:** continue recording for at least `2 s`.

The no-occlusion condition follows the same start, motion, endpoint, and hold sequence without deliberately hiding the tag.

The maneuver condition uses one marked turn point and one predeclared direction change. Do not improvise additional turns.

## Timing and acceptance

The target measurement-gap duration is measured from the recorded vision stream, not from the operator's subjective count.

For occlusion conditions:

- accept a trial when the measured gap is within `±0.25 s` of the target duration;
- otherwise reject it and record `rejection_reason`;
- do not delete rejected trials;
- do not replace a rejected trial silently;
- replacement trials receive a new `trial_id` and preserve the rejected entry.

## Primary metrics

For each accepted endpoint trial, compute both trackers from the same timestamps and truth:

1. **Endpoint prediction error**
   Euclidean distance between the tracker estimate immediately before the first reacquired measurement update and the measured stationary endpoint.

2. **First-reacquisition error**
   Euclidean distance between the first measurement-backed tracker estimate after reveal and the measured endpoint.

3. **Reacquisition latency**
   Time from the first returning valid vision measurement to the first measurement-backed tracker status.

4. **Failure/reset indicator**
   Whether the tracker became uninitialized, reset, emitted invalid output, or failed to reacquire during the hold window.

Secondary metrics:

- measurement-gap duration;
- maximum measurement age;
- maximum prediction-only steps;
- covariance trace at endpoint;
- IMM mode probabilities at occlusion start and endpoint;
- MH relative hypothesis weights at occlusion start and endpoint;
- CPU, memory, and temperature when runtime instrumentation is available.

## Pairing rule

IMM and MH outputs are paired only when they come from the same accepted trial and the same evaluation timestamp definition.

Do not pair trials collected under different:

- camera positions;
- endpoint coordinates;
- camera-control configurations;
- condition definitions;
- truth methods.

## Statistical analysis

Analyze each condition separately.

For continuous paired error metrics:

- report sample count;
- report IMM and MH median error;
- report median `MH - IMM` difference;
- report median error reduction;
- use `2,000` bootstrap resamples with a fixed seed;
- report the bootstrap 95% confidence interval;
- report the Wilcoxon signed-rank result when SciPy is available.

Use:

```bash
python3 ghost_sim_ros2/analysis/statistical_comparison.py \
  --imm-errors <comma-separated-values> \
  --mh-errors <comma-separated-values> \
  --condition <condition_id> \
  --n-boot 2000 \
  --seed 260710 \
  --out <condition_summary.json>
```

Do not pool different occlusion durations into one significance test. Report effect size and confidence interval even when the p-value is not significant.

For failure/reset outcomes, report counts and rates by tracker and condition. Do not apply the continuous-error harness to binary failures.

## Randomization and run order

Use manifest field:

```text
randomization_seed: 260710
```

Generate the order before collection, in blocks that keep camera geometry fixed. Preserve the generated order as a file in the campaign directory.

Allowed operational deviations:

- safety stop;
- equipment failure;
- camera-control failure;
- accidental movement;
- invalid measurement-gap duration.

Every deviation must be logged. Do not reorder trials because early results look favorable or unfavorable.

## Required campaign artifacts

```text
campaign_manifest.json
campaign_validation_before.json
randomized_trial_order.csv
setup_photo_or_diagram.*
camera_controls_before.txt
camera_controls_after_each_block.txt
trial_directories/
campaign_validation_after.json
condition_summaries/
campaign_summary.md
campaign_summary.json
```

Each accepted trial directory should retain at minimum:

```text
metadata.json
vision_pose.jsonl
imm_futures.jsonl
mh_futures.jsonl
status.jsonl
events.jsonl
metrics.jsonl
summary.json
summary.md
```

## Manifest validation

Validate the template structure:

```bash
python3 ghost_sim_ros2/analysis/validate_campaign_manifest.py \
  ghost_sim_ros2/docs/IMM_MH_CAMPAIGN_MANIFEST.example.json
```

The template is structurally valid but intentionally emits a warning while `protocol_commit` is `0000000`. Before collecting data, copy the template to the campaign directory, replace that placeholder with the merged protocol commit, set `protocol_commit_status` to `PINNED_BEFORE_COLLECTION`, and save the validation output.

Validate the completed campaign:

```bash
python3 ghost_sim_ros2/analysis/validate_campaign_manifest.py \
  campaign_manifest.json \
  --require-complete \
  --out campaign_validation_after.json
```

A non-zero exit status means the manifest is not valid for the requested state.

## Rejection criteria

Reject a trial when any of the following occurs:

- camera or endpoint marker moves;
- tag detaches or changes geometry;
- camera controls drift outside the recorded configuration;
- endpoint is not reached and held;
- target path violates the predeclared condition;
- measured occlusion duration is outside tolerance;
- required IMM or MH logs are absent;
- timestamps are non-monotonic or unusable;
- operator touches the camera or mount;
- trial metadata cannot be matched to the manifest.

Rejected trials remain in the evidence package with their reasons.

### Outcome-independent rejection lock

A run may be rejected only for an acquisition or protocol failure that is identifiable without comparing IMM and MH performance. The update tool accepts only these predeclared codes:

- `CAMERA_OR_ENDPOINT_MARKER_MOVED`
- `TAG_GEOMETRY_CHANGED`
- `CAMERA_CONTROLS_DRIFTED`
- `ENDPOINT_NOT_REACHED_OR_HELD`
- `PATH_PROTOCOL_VIOLATION`
- `OCCLUSION_GAP_OUTSIDE_TOLERANCE`
- `REQUIRED_LOGS_MISSING`
- `TIMESTAMPS_NONMONOTONIC_OR_UNUSABLE`
- `CAMERA_OR_MOUNT_TOUCHED`
- `TRIAL_METADATA_MISMATCH`

Tracker error magnitude, which tracker won, effect size, statistical significance, visual appearance of a plot, or whether a trial helps or harms a desired claim are never valid rejection criteria. Such results remain in the accepted paired analysis when the acquisition and protocol checks pass. Free-text details belong in operator notes; they do not replace the canonical code.

## Required final language

Before accepted data exist:

```text
Campaign status: PREDECLARED_PENDING_COLLECTION
Comparison status: NO_REAL_PAIRED_SUPERIORITY_CLAIM
```

After collection but before analysis passes:

```text
Campaign status: COLLECTED_PENDING_QUALITY_AND_STATISTICAL_REVIEW
Comparison status: NO_SUPERIORITY_CLAIM_PENDING_REVIEW
```

Only condition-specific conclusions supported by the accepted paired data, confidence intervals, and documented limitations may be published.
