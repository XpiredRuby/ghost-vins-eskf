# GHOST-X Interactive Showcase Evidence Checklist

This checklist maps the interactive page's headline claims to retained evidence. The page must not publish a number or conclusion outside this map.

| Page claim or section | Evidence source | Data class | Sample basis / boundary |
|---|---|---|---|
| 2.45097017288208 s intended hardware occlusion; reacquired without reset | `GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json` | Measured hardware | N=1 intended dropout |
| 24/24 controlled-truth trials accepted | `GHOST_X_G4_VALIDATION.json`, `GHOST_X_G10_CI_REPORT.json` | Synthetic software | N=24 trials, 8 scenario families |
| 12/12 software-injected faults passed | `GHOST_X_G8_FAULT_REPORT.json`, `.csv`, `g8_fault_evidence/*.jsonl` | Synthetic software | N=12 cases; pass means correct detection, isolation, and accepted recovery on one shared canonical stream |
| RT-002 observed 3.4433068896378227 Hz versus 29.7 Hz minimum | `GHOST_X_G9_RUNTIME_REPORT.json` | Measured hardware runtime | Requirement not met |
| Follower-drone navigation/reacquisition behavior | `GHOST_DRONE_MISSION_VALIDATION.json` | Synthetic software | One deterministic local-frame mission; no physical flight |
| Raspberry Pi 4B, eMeet C960, ROS 2 Jazzy, AprilTag identity | `GHOST_X_BASELINE_MANIFEST.json`, `GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json` | Measured hardware | Guided tabletop campaign |
| Interactive replay measurements, events, and tracker states | `data/GHOST_HARDWARE_REPLAY_20260716.json` plus embedded source hashes | Measured hardware | Browser cue window only; no interpolation or video |
| CV / formal IMM / GHOST-MH overall and hidden RMSE | `GHOST_X_G10_CI_REPORT.json` | Synthetic software | Identical inputs, N=24 |
| Matched Python-reference runtime rows | `GHOST_X_G9_RUNTIME_REPORT.json` | Measured hardware runtime | Raspberry Pi, no stress workers |
| Short-hide, lateral, stationary and range results | `GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json`, `guided_hardware_evidence/*.json` | Measured hardware | Guided sequences; correlated samples are not independent trials |
| Long-hide mission occlusions | `GHOST_DRONE_MISSION_VALIDATION.json` | Synthetic software | N=2 occlusions in one mission |
| Runtime pass/fail and deadline evidence | `GHOST_X_G9_RUNTIME_REPORT.json`, `.csv` | Measured hardware runtime | RT-001 and RT-002 failed; RT-003 passed; 11/12 estimator max-time rows met the deadline |
| 34/34 requirement traceability | `GHOST_X_FINAL_TRACEABILITY.csv`, `GHOST_X_SOFTWARE_STATUS.json` | Verification | 34 mapped rows |
| Limitations and rejected evidence | `GHOST_X_CLAIM_BOUNDARIES.md`, `GHOST_X_APPROVED_CLAIMS.json`, `GHOST_X_FAILURE_GALLERY.json` | Claim governance | Permanent page section |

## Metrics intentionally shown as unavailable

- Symmetric reacquisition time for CV, formal IMM, and GHOST-MH on one common retained campaign.
- Symmetric reset count for all three estimators on one common retained final comparison campaign.
- Metrology-grade physical target truth.
- Physical closed-loop drone-flight results.
- Physical ICM-42688-P identity/rate/data validation for this campaign.
- Approved camera footage or setup photographs.
- Outdoor or adversarial visual-target hardware results.
- Hard-real-time certification or flight-worthiness evidence.

## Presentation rules

- Measured hardware, synthetic software, and verification evidence use visibly different badges.
- Null metrics render as “Not retained,” never as zero.
- Replay points are recorded samples only. Tracker points may be downselected from recorded samples but are never interpolated.
- Equal tracker comparison charts use identical scales and identical metric definitions.
- Failures and null results remain visible.
