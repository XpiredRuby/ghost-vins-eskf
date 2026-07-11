# GHOST Recruiter-Facing Hero Demonstration Protocol

## Purpose

Create a visually clear 45–60 second hardware replay that communicates intermittent vision, formal IMM prediction, GHOST-MH futures and reacquisition to a recruiter without misrepresenting the take as statistical accuracy evidence.

## Evidence status

```text
Artifact type: REPRESENTATIVE_PRESENTATION_DEMONSTRATION
Not used as: FORMAL_CAMPAIGN_STATISTICAL_SAMPLE_OR_ACCURACY_VALIDATION
```

## Three-take rule

Record exactly three planned takes under the same camera configuration when possible:

```text
hero_take_01
hero_take_02
hero_take_03
```

Preserve all three. The selected public take must be documented in `hero_selection_record.json` with:

- all three artifact paths;
- objective eligibility checks;
- selected take;
- selection reason;
- statement that no unlisted takes were discarded;
- statement that selection was for explanatory clarity, not best numerical performance.

## Physical layout

Use a path that fills substantially more of the camera plane than the existing narrow nearly vertical trajectory while remaining inside the calibrated operating area.

Mark:

- start point in the lower-left or lower-center region;
- first diagonal segment;
- first direction change;
- second broad segment;
- final endpoint;
- occluder locations or operator positions for 1-, 2- and 3-second gaps.

The USB webcam and mount remain fixed. The tag stays rigid and approximately fronto-parallel enough for reliable detection while visible.

## Planned choreography

Target total: approximately 50 seconds.

| Time block | Operator action | Intended visual story |
|---|---|---|
| 0–5 s | Tag visible and stationary at start | Stable measurement lock and estimator initialization |
| 5–11 s | Smooth diagonal motion | Both trackers follow a clear 2D path |
| 11–12 s | Hide for requested 1 s | Short prediction-only behavior |
| 12–17 s | Reveal and continue | Fast reacquisition and correction |
| 17–24 s | Broad direction change and lateral motion | Motion-model probabilities and hypothesis behavior become visible |
| 24–26 s | Hide for requested 2 s | Medium dropout with uncertainty growth |
| 26–32 s | Reveal, continue through second segment | Reacquisition after a longer gap |
| 32–38 s | Smooth maneuver toward final endpoint | Demonstrates nontrivial trajectory coverage |
| 38–41 s | Hide for requested 3 s while reaching endpoint | Longest bounded prediction interval |
| 41–48 s | Reveal and hold at endpoint | Reacquisition, settling and final truth context |
| 48–52 s | Post-roll stationary | Clean ending for replay and editing |

Measured gaps from the vision log are reported on the replay. The table describes requested choreography and does not override recorded timing.

## Eligibility checks for a public take

A take is eligible only when:

- the camera and mount did not move;
- camera controls remained in the recorded configuration;
- the tag was visible during every intended visible interval;
- all three requested dropout events occurred;
- both IMM and MH logs are present;
- the replay contains no unexplained estimator reset;
- the path remains inside the declared workspace;
- the recording contains no private screen, network or account information;
- the take is packaged and checksum-verified.

A take may still be preserved but marked ineligible when one of these checks fails.

## Selection rule

Among eligible takes, select the take using this priority order:

1. all three actual measured gaps are within ±0.25 seconds of their requested durations;
2. no missing tracker or vision logs;
3. no camera-control or physical-integrity failure;
4. greatest two-dimensional path coverage measured by bounding-box area;
5. fewest unintended visible-frame detection losses;
6. lowest trial ID as deterministic tie-breaker.

Do not select solely because one take gives the smallest endpoint error.

## Public replay requirements

The hero replay should show:

- synchronized video when available;
- raw AprilTag measurements;
- formal IMM estimate;
- GHOST-MH estimate/futures;
- visible/hidden timeline;
- actual measured gap duration;
- measurement age;
- prediction-only steps;
- IMM mode probabilities;
- MH relative hypothesis weights;
- covariance/uncertainty where valid;
- clear labels at each hide and reacquisition event;
- a banner that the take is a representative demonstration, not a statistical result.

## Website pairing

The hero replay should be presented beside aggregate evidence rather than alone:

- controlled-R covariance card;
- grid bias/RMSE card;
- error-versus-gap result;
- paired IMM/MH distribution;
- reacquisition-latency distribution;
- failure-rate card;
- USB hardware/BOM link;
- full technical report.

This gives recruiters a strong visual entry point while engineers retain the complete validation trail.
