# GHOST Phase 2 Consolidated Operator Session

## Purpose

Collect every remaining physical input in one controlled session after Phase 1 software, tooling, evidence, and candidate-parameter preparation are complete.

The operator moves or occludes the AprilTag only when prompted. The Pi workflow controls camera settings, ROS nodes, timing, recording, validation, trial identity, acceptance checks, evidence preservation, and analysis inputs.

## Non-negotiable integrity rules

- Keep the camera, mount, cable, lighting, and coordinate frame unchanged unless the workflow explicitly pauses and records a configuration change.
- Preserve every run, including failed and rejected runs.
- Reject only for a predeclared acquisition or protocol failure code.
- Never reject or exclude a run because IMM or MH performed poorly, because one tracker won, because a plot looks unfavorable, or because the result weakens significance.
- Dry runs are never included in formal statistics.
- Formal parameter locking occurs only after all six dry runs pass and before formal outcomes are reviewed.

## Human-work sequence

### Block A — Six-point measured grid

1. Confirm the coordinate origin and axes.
2. Measure and mark six non-collinear tag locations spanning useful x and y variation.
3. Place and hold the rigid tag carrier at each prompted point.
4. Record the measured truth coordinates before evaluating camera error.

The grid validates static position accuracy and establishes measured start, endpoint, and turn locations for the campaign.

### Block B — Six campaign dry runs

Perform one non-statistical run for each condition:

1. `static_visible`
2. `endpoint_no_occlusion`
3. `endpoint_occ_1s`
4. `endpoint_occ_2s`
5. `endpoint_occ_3s`
6. `maneuver_occ_2s`

The workflow checks motion choreography, actual recorded gap duration, endpoint hold, log completeness, trial metadata, and recorder integrity. Parameter changes are allowed only during this dry-run block and must be documented.

### Automated checkpoint — lock and initialize

After all dry runs pass, the Pi workflow will:

1. save camera-control and ROS-parameter snapshots;
2. create the formal parameter lock;
3. verify the repository is clean and commit-pinned;
4. expand and freeze the balanced randomized 55-slot plan;
5. generate the trial order and operator cues;
6. verify the lock immediately before collection.

No physical action is required during this checkpoint.

### Block C — Formal 55-trial paired campaign

Exact planned matrix:

| Condition | Planned trials |
|---|---:|
| `static_visible` | 5 |
| `endpoint_no_occlusion` | 10 |
| `endpoint_occ_1s` | 10 |
| `endpoint_occ_2s` | 10 |
| `endpoint_occ_3s` | 10 |
| `maneuver_occ_2s` | 10 |
| **Total** | **55** |

For each dynamic trial:

1. Hold the tag at the prompted start mark for pre-roll.
2. Move along the marked path when cued.
3. Apply the prompted occlusion when required.
4. Stop at the measured endpoint before or at reveal.
5. Reveal and hold still through post-roll.

For each static trial, hold the tag rigidly at the prompted measured point for the full recording.

The recorded vision stream—not human counting—determines actual occlusion duration. Formal analysis uses paired IMM and MH outputs from the same accepted acquisition.

### Block D — Runtime evidence and hero takes

1. Repeat representative visible, dropout, and maneuver blocks while runtime monitoring records CPU, memory, temperature, and timing.
2. Perform three preserved recruiter-facing hero takes.
3. Do not delete or overwrite unselected takes; selection is presentation-only and separate from formal statistics.

## Canonical rejection codes

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

Free-text notes may describe what happened but cannot create a new post-hoc rejection rule.

## Expected operator burden

- Active hands-on work: approximately `1.5-2.5 hours`.
- Total time near the setup, including automated checks and checkpoints: approximately `3-4 hours`.
- The session may pause only at a recorded checkpoint; the camera configuration and evidence state must be verified again before resuming.

## Phase 2 start gate

Do not begin until Phase 1 reports all of the following:

- repository clean and pushed;
- final build and test evidence passing;
- live camera continuity result documented;
- accepted direct stationary covariance candidate documented;
- Phase 2 candidate parameter YAML present;
- campaign rejection lock tested;
- session evidence updated;
- no camera or ROS collection process left running.
