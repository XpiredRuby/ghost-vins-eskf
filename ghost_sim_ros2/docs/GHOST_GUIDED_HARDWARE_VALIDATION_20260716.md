# GHOST Guided Hardware Validation — 2026-07-16

## Verdict

**PASS for guided relative response and short-dropout reacquisition.**

This campaign verified camera-calibrated AprilTag response to left, right, closer and farther operator-guided motion, plus successful reacquisition after a measured 2.451 s vision loss. It does not establish absolute position accuracy, flight performance or universal estimator superiority.

## Test configuration

- Camera: eMeet C960 at `/dev/video0`
- AprilTag: `tag36h11`, ID 0, nominal edge length 0.100 m
- Camera calibration RMS reprojection error: 0.6484 px
- Measurement covariance source: `CONTROLLED_R_CANDIDATE_STABLE_60S_PENDING_ENGINEER_REVIEW`
- Measurement timeout: 0.30 s
- GHOST-MH maximum occlusion: 3.0 s
- Browser conductor: live preview, local audio cues and monotonic client-side timers
- Evidence scope: guided tabletop relative response; no independent metrology-grade ground truth

## Accepted evidence

### Lateral response

The measured lateral coordinate changed in the expected direction:

| Hold | Mean y (m) |
|---|---:|
| Center baseline | 0.0265 |
| Left | 0.4022 |
| Right | -0.4126 |

This supports directional relative response, not absolute lateral accuracy.

### Short dropout and reacquisition

- Browser occlusion cue: 1.996 s
- Measured vision loss: 2.451 s
- Reacquisition: successful
- Reset during the intended dropout: none
- GHOST-MH top-1 reacquisition proxy error: 0.00262 m
- Constant-velocity proxy error: 0.04841 m
- GHOST-MH improvement versus constant velocity: 94.6%
- Last-seen hold proxy error: 0.000657 m

GHOST-MH strongly outperformed the constant-velocity baseline for this event. The stationary last-seen hold remained better, so this result does not support a universal superiority claim.

### Farther response

The accepted farther segment used the distance-only retest:

- Baseline x: 1.0364 m
- Farther x: 1.2852 m
- Relative change: +0.2488 m
- Valid hold samples: 89
- Hold standard deviation in x: 0.00169 m
- Maximum internal sample gap: 0.0755 s
- Final-center difference from baseline: 0.00286 m

### Closer response

The accepted closer segment used the smaller closer-only retest:

- Baseline x: 1.0374 m
- Closer x: 0.6934 m
- Relative change: -0.3440 m
- Valid hold samples: 32
- Hold standard deviation in x: 0.0158 m
- Maximum internal sample gap: 0.317 s
- Resets during the sequence: 0
- Final-center difference from baseline: 0.0122 m

The observed pose change is a relative camera estimate. It must not be described as a tape-measured physical displacement.

## Rejected or limited evidence

The original floor-grid attempt is rejected because the camera/tag geometry was not actually changed between nominal grid captures. Its computed absolute-error values must not be used.

The first combined distance attempt was partial: the farther segment passed, while the closer segment had insufficient stable samples and the sequence contained one reset. The later closer-only retest replaced only that failed coverage item.

The controlled-R matrix remains a stable-window candidate pending engineering review. Tracker status remains `cal=UNSPECIFIED`; therefore, the campaign must not be called hardware-accuracy calibrated.

## Safe claims

- The calibrated camera publisher produced expected relative left/right and closer/farther pose response.
- GHOST-MH maintained bounded prediction and reacquired after a measured 2.451 s short dropout without resetting during that intended event.
- For that short-dropout event, GHOST-MH top-1 error was substantially lower than constant velocity.
- The single-command browser conductor provided repeatable local cues, live preview, evidence capture and controlled shutdown.

## Unsafe claims

- Absolute positioning accuracy or floor-grid RMSE
- Certification-grade calibration
- Flight or autonomous-drone validation
- SLAM, VIO or GPS-denied localization
- GHOST-MH always outperforming all baselines
- The hand-guided distance changes equaling specific physical distances

## Evidence index

- [Combined machine-readable verdict](GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json)
- [Full guided-sequence summary](guided_hardware_evidence/20260716_guided_sequence_summary.json)
- [Distance-only summary](guided_hardware_evidence/20260716_distance_only_summary.json)
- [Closer-only summary](guided_hardware_evidence/20260716_closer_only_summary.json)
- [Browser launcher runbook](GUIDED_HARDWARE_LAUNCHER.md)

The raw high-rate logs remain outside Git under `/home/xpired/ghost_trials/physical_validation_20260711T183400Z/browser_guided_runs/`.
