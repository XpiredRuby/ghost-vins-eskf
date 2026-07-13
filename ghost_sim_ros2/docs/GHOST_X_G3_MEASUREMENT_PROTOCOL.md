# GHOST-X Phase G3 — Measurement Characterization Protocol

## Current status

**Software preparation:** COMPLETE  
**Physical campaign:** NOT YET COLLECTED  
**Protocol version:** `ghost-x-g3-v1`

G3 is complete only after all required multi-range/orientation trials pass the predeclared quality gates and the aggregate covariance-model report is generated. The existing `controlled_R_direct_01` trial remains useful baseline-v0 evidence but does not satisfy the multi-condition G3 exit criteria.

## Objective

Characterize AprilTag camera-position measurements across controlled range and yaw conditions while separating:

1. short-window measurement dispersion;
2. fixture-referenced bias;
3. drift and temporal correlation;
4. Gaussianity diagnostics;
5. calibration/fixture uncertainty that cannot be isolated from repeated measurements alone.

This phase does not evaluate dynamic tracker accuracy or estimator superiority.

## Frozen design

| Factor | Levels |
|---|---|
| Range | `0.70 m`, `1.05 m`, `1.40 m` |
| Yaw | `-20°`, `0°`, `+20°` |
| Repeats | `2` per condition |
| Conditions | `9` |
| Planned accepted trials | `18` |
| Capture duration | `90 s` of valid poses |
| Analysis window | fixed `[15, 75) s` |
| Minimum samples in window | `600` |
| Minimum rate | `10 Hz` |
| Maximum gap | `0.25 s` |

Trial order is deterministically randomized with seed `20260713` when the campaign is initialized.

## No-purchase fixture

Use a borrowed measuring tape, existing measured floor marks, or university lab markings. Do not buy a new sensor or metrology system.

Declared fixture uncertainties:

- range: `±0.01 m`;
- lateral centering: `±0.005 m`;
- yaw: `±2°`.

These are fixture uncertainty declarations, not camera accuracy results.

## Locked hardware and software

The following remain unchanged across formal trials:

- Raspberry Pi and USB port;
- EMEET C960 camera and `/dev/video0`;
- camera mount and height;
- `640 × 480` MJPEG capture;
- AprilTag family and printed tag;
- tag physical size `0.10 m`;
- camera calibration artifact;
- manual exposure, gain, white balance, and power-line settings;
- repository protocol commit;
- G3 design hash;
- capture and analysis tools.

Any setup change requires a new campaign identifier or a formally recorded discrepancy.

## Target placement

For each trial:

1. Place the AprilTag center at the declared range from the camera reference plane.
2. Align the tag center to the lateral-zero mark.
3. Set the declared yaw relative to front-facing zero.
4. Keep pitch and roll nominally zero.
5. Keep the target, camera, table, and lighting stationary.
6. Wait at least `15 s` after setup before capture begins.
7. Do not touch the target during the `90 s` recording.

The operator does not choose a “stable-looking” analysis interval. The analyzer always uses `[15, 75) s`.

## Campaign initialization

After the G3 preparation commit is frozen:

```bash
python3 ghost_sim_ros2/tools/init_ghost_x_g3_campaign.py \
  --design ghost_sim_ros2/config/ghost_x_g3_measurement_campaign.yaml \
  --out ~/ghost_trials/ghost_x_g3_measurement_v1 \
  --calibration "$GHOST_CALIBRATION_ARTIFACT" \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf
```

This creates:

- immutable campaign manifest;
- design snapshot and hashes;
- randomized trial order;
- 18 trial manifests;
- one directory per trial.

## One-trial capture

Only after the tag is placed at the sequence’s declared geometry:

```bash
python3 ghost_sim_ros2/tools/collect_ghost_x_g3_trial.py \
  --campaign-dir ~/ghost_trials/ghost_x_g3_measurement_v1 \
  --sequence <N> \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf \
  --calibration "$GHOST_CALIBRATION_ARTIFACT"
```

The runner:

1. locks and verifies camera controls;
2. captures direct AprilTag/SolvePnP measurements;
3. exports raw `t,x,y,z` CSV;
4. runs fixed-window continuity gates;
5. hashes artifacts;
6. preserves every attempt;
7. accepts or rejects the attempt without deleting it.

A failed attempt may be repeated only after its failure reason is recorded.

## Required diagnostics

Each acceptable trial reports:

- sample rate, sample count, maximum gap;
- mean position;
- fixture-referenced bias;
- raw and linearly detrended covariance;
- `x-y` cross-correlation;
- linear drift slopes;
- brightness and AprilTag decision margin;
- skewness and excess kurtosis;
- Jarque–Bera Gaussianity diagnostic;
- lag-1 autocorrelation;
- Ljung–Box whiteness diagnostics at lags `5`, `10`, and `20`.

A p-value above `0.05` means the test did not reject the assumption; it is not proof that the assumption is true.

## Candidate covariance models

Four models are frozen before collection:

1. one constant full `2 × 2` covariance;
2. log variance linear in range with fixed correlation;
3. log variance linear in range and absolute yaw with fixed correlation;
4. per-condition covariance with `25%` shrinkage toward the pooled covariance.

Selection uses leave-one-trial-out Gaussian negative log likelihood with the predeclared complexity penalty:

```text
score = 2 × held-out NLL + k × log(total validation samples)
```

When scores differ by less than `2%`, the lower-parameter model is selected.

## Aggregate analysis

```bash
python3 ghost_sim_ros2/analysis/measurement_characterization.py \
  --campaign-dir ~/ghost_trials/ghost_x_g3_measurement_v1 \
  --out-dir ~/ghost_trials/ghost_x_g3_measurement_v1/analysis
```

Generated artifacts:

- `measurement_characterization.json`;
- `measurement_characterization.md`;
- `trial_summary.csv`;
- selected covariance model and parameters;
- retained invalid/missing-trial list.

## Software readiness verification

| Check | Result |
|---|---|
| G3 readiness validator | PASS — 18 trials, 9 conditions, 0 errors |
| Synthetic full campaign | PASS — all 18 trials analyzed and covariance model selected |
| Focused G0–G3 regression | PASS — 23 tests |
| Full package regression | PASS — 228 passed, 1 skipped in 193.30 s |
| Python compilation | PASS |
| ROS 2 package build | PASS |

This verifies the collection and analysis workflow, not the physical camera results.

## G3 exit criteria

G3 passes only when:

- all 9 conditions have acceptable evidence;
- at least 18 accepted trials exist;
- failed and invalid attempts remain preserved;
- raw and detrended residual diagnostics are reported;
- covariance candidates are compared through the frozen held-out rule;
- one covariance model is selected or an explicit no-selection result is defended;
- fixture and calibration uncertainty limitations remain explicit.
