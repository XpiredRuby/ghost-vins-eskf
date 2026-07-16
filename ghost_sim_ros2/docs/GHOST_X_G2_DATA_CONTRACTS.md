# GHOST-X Phase G2 — Frames, Timing, and Data Contracts

## Status

**Phase status:** COMPLETE  
**Contract version:** `ghost-x-data-contract-v1`  
**Schema version:** `1`  
**Runtime schema probe:** PASS — 5 of 5 topics validated

Machine-readable sources:

- `config/ghost_x_data_contract.yaml`
- `schemas/formal_imm_futures.schema.json`
- `schemas/ghost_mh_futures.schema.json`
- `schemas/tracker_status.schema.json`
- `schemas/mission_validation.schema.json`
- `docs/GHOST_X_G2_RUNTIME_VALIDATION.json`
- `docs/GHOST_X_G2_VALIDATION.json`

## Frame contract

### `camera`

Hardware single-camera AprilTag estimator frame:

- right-handed after the active publisher remapping;
- `+x`: forward range from camera;
- `y`: lateral camera-space displacement;
- `z`: unused by the current planar estimator;
- negative `x` is rejected by hardware tracker defaults.

The simulation-only signed-coordinate parameter does not alter this hardware default.

### `ghost_local`

Deterministic software mission map:

- right-handed;
- `+x`: local map east/right;
- `+y`: local map north/up;
- `+z`: local vertical up;
- observer, target truth, estimator output, obstacle geometry, and guidance are evaluated in this frame.

### Truth frame

Formal truth must either use the estimator evaluation frame directly or include an explicit transform and transform provenance. Frame-name similarity is not accepted as proof of equivalence.

## Units and covariance

All formal outputs use SI units:

| Quantity | Unit |
|---|---|
| Position | `m` |
| Velocity | `m/s` |
| Acceleration | `m/s²` |
| Angle | `rad` |
| Angular rate | `rad/s` |
| Position covariance | `m²` |
| Velocity covariance | `(m/s)²` |
| Time and latency | `s` |

Planar state order:

```text
[x_m, y_m, vx_mps, vy_mps]
```

Covariance must be finite, dimensionally correct, symmetric within `1e-10`, and positive semidefinite within a minimum-eigenvalue tolerance of `-1e-10`.

Estimator covariance is not ground-truth uncertainty and may not be presented as physical accuracy without controlled truth.

## Timestamp contract

Every versioned JSON payload contains:

- `source_time_s`: sensor or simulator source timestamp;
- `receipt_time_s`: consumer callback receipt timestamp;
- `processing_time_s`: estimator processing completion timestamp;
- `publication_time_s`: output publication timestamp.

When timestamps share a synchronized clock, expected ordering is:

```text
source <= receipt <= processing <= publication
```

When synchronization is not established, values are retained but end-to-end latency claims are prohibited.

## Measurement validity behavior

| Condition | Required behavior |
|---|---|
| Fresh accepted measurement | `VALID_TRACKING` |
| Bounded propagation without fresh measurement | `VALID_PREDICTION_ONLY` |
| Declared prediction/fault limit exceeded | `DEGRADED` |
| Estimator not initialized | `WAITING_FOR_TARGET` |
| Nonfinite or unusable state | `INVALID` |
| Completed accepted software mission | `MISSION_COMPLETE` |

Stale, duplicate, out-of-order, nonfinite, invalid-range, and corrupt-covariance inputs must be counted and rejected or handled by an explicitly identified algorithm. Silent acceptance is prohibited.

## Provenance contract

Every G2 JSON payload contains:

```text
provenance.calibration_id
provenance.configuration_id
provenance.configuration_label
```

Identifiers use SHA-256 where an artifact or effective configuration is available. Software-only runs may use `UNSPECIFIED` calibration. Formal hardware evidence may not.

For formal hardware runs, set the tracker parameter:

```text
calibration_artifact_path:=/absolute/path/to/calibration.json
```

or export `GHOST_CALIBRATION_ARTIFACT=/absolute/path/to/calibration.json` before launching. Acceptance tooling must reject formal hardware evidence whose calibration identifier is `UNSPECIFIED`.

Configuration identifiers are derived from effective runtime parameters, not a filename alone.

## Versioned runtime outputs

Existing human-readable status topics remain available:

```text
/ghost/tracker_imm/status
/ghost/tracker_mh/status
```

New machine-readable status topics:

```text
/ghost/tracker_imm/status_json
/ghost/tracker_mh/status_json
```

Versioned futures topics retain existing fields and add the contract envelope:

```text
/ghost/tracker_imm/futures_json
/ghost/tracker_mh/futures_json
```

Mission evaluation output also uses the contract envelope:

```text
/ghost/evaluation/status_json
```

## Runtime validation result

A clean deterministic mission run validated the actual live payloads from:

1. formal IMM futures;
2. GHOST-MH futures;
3. formal IMM status JSON;
4. GHOST-MH status JSON;
5. mission evaluation JSON.

All five passed their versioned JSON schemas with no missing topics or validation errors.

The contract-compliant mission also passed its operational acceptance criteria:

- two obstacle-caused occlusions;
- two reacquisitions;
- zero collisions;
- zero boundary violations;
- both estimators publishing during occlusion.

## Historical evidence policy

Bags recorded before G2 are immutable **baseline-v0** evidence. Their raw messages do not contain the complete G2 contract envelope.

They are preserved and identified through `GHOST_X_BASELINE_MANIFEST.json`. Calibration or configuration identifiers shall never be retroactively inserted into historical raw messages.

## Software verification

Final G2 verification on Raspberry Pi 4 / ROS 2 Jazzy:

| Check | Result |
|---|---|
| Python compilation | PASS |
| G2 phase validator | PASS — 4 schemas, 5 runtime topics, 0 errors |
| Focused G0/G1/G2/mission tests | PASS — 20 tests |
| Full package regression | PASS — 225 passed, 1 skipped in 188.69 s |
| ROS 2 package build | PASS |
| Live-process cleanup | PASS — no mission/tracker stack left running |

## G2 exit review

| Exit item | Result |
|---|---|
| Frames and axes defined | PASS |
| SI units and covariance ordering defined | PASS |
| Source/receipt/process/publication times defined | PASS |
| Stale/duplicate/OOS/nonfinite behavior defined | PASS |
| Versioned schemas added | PASS |
| Formal IMM futures schema-valid at runtime | PASS |
| GHOST-MH futures schema-valid at runtime | PASS |
| Tracker status JSON schema-valid at runtime | PASS |
| Mission metrics schema-valid at runtime | PASS |
| Calibration/config identifiers embedded in future recorded JSON | PASS |
| Historical bag non-retrofit policy documented | PASS |

**G2 exit decision:** APPROVED TO ENTER G3.
