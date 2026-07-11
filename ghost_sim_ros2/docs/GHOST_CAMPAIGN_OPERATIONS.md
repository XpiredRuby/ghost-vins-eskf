# GHOST Campaign Initialization and Trial Conductor

## Purpose

Convert the predeclared 55-trial IMM/MH protocol into a pinned, randomized, directory-complete campaign before physical data are observed—and provide local browser cues that do not depend on chat or network latency.

## Claims boundary

```text
Campaign operations status: SOFTWARE_PREPARATION_COMPLETE_PENDING_PHYSICAL_EXECUTION
Timing acceptance source: RECORDED_VISION_GAP_NOT_BROWSER_CUE_ALONE
```

The conductor helps the operator perform repeatable choreography. It does not prove that the actual AprilTag measurement gap matched the requested duration; the recorded vision stream remains the acceptance source of truth.

## Initialize the campaign

From the repository root:

```bash
python3 ghost_sim_ros2/tools/campaign_operations.py \
  --template ghost_sim_ros2/docs/IMM_MH_CAMPAIGN_MANIFEST.example.json \
  --out ~/ghost_trials/imm_mh_campaign_v1 \
  --resolve-protocol-commit \
  --repo-root .
```

The initializer:

- resolves and pins the committed campaign protocol revision;
- rejects zero or malformed commit placeholders;
- expands the six conditions into all 55 planned trial entries;
- generates deterministic balanced-block randomization using seed `260710` unless overridden;
- writes `randomized_trial_order.csv`;
- creates all 55 trial directories;
- creates one `conductor_plan.json` and `trial_metadata.json` per trial;
- runs the existing campaign-manifest validator;
- writes `campaign_validation_before.json`;
- hashes the pinned manifest, order and validation output into `campaign_lock.json`;
- refuses to overwrite a non-empty campaign directory.

Expected top-level output:

```text
imm_mh_campaign_v1/
├── CAMPAIGN_README.md
├── campaign_lock.json
├── campaign_manifest.json
├── campaign_validation_before.json
├── randomized_trial_order.csv
└── trial_directories/
    ├── <trial_id>/conductor_plan.json
    ├── <trial_id>/trial_metadata.json
    └── ...
```

## Balanced randomization

The initializer uses one trial from each eligible condition per repetition round and shuffles within that round using the fixed seed. This prevents all 1-second trials, all 2-second trials, and all 3-second trials from being collected in large result-correlated blocks while preserving deterministic reproducibility.

The generated order must not be changed because early outcomes look favorable or unfavorable. Safety, equipment, camera-control, physical-disturbance and invalid-gap deviations remain allowed only when logged.

## Start one trial conductor

Start the recorder and trackers first. Then run:

```bash
python3 ghost_sim_ros2/tools/trial_conductor.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --sequence 1 \
  --host 127.0.0.1 \
  --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

The page provides:

- large full-screen visual cues;
- browser speech and a short audio tone;
- `performance.now()` countdown timing;
- pause/resume;
- required rejection reason on stop;
- server-side `conductor_events.jsonl` logging;
- downloadable local event copy;
- trial ID, condition and randomized sequence display.

## Predeclared cue profiles

### Stationary visible

```text
HOLD START 3 s
STATIONARY SAMPLE 10 s
POST-ROLL 2 s
DONE
```

### Straight endpoint without intentional occlusion

```text
HOLD START 3 s
MOVE 2 s
ENDPOINT 1 s
HOLD END 5 s
POST-ROLL 2 s
DONE
```

### Straight endpoint with 1/2/3-second requested gap

```text
HOLD START 3 s
MOVE 2 s
OCCLUDE NOW 1/2/3 s
REVEAL
HOLD END 5 s
POST-ROLL 2 s
DONE
```

### Maneuver with 2-second requested gap

```text
HOLD START 3 s
MOVE TO TURN 2 s
TURN 1 s
OCCLUDE NOW 2 s
REVEAL
HOLD END 5 s
POST-ROLL 2 s
DONE
```

The motion and turn durations are operator choreography aids. Endpoint truth, actual path compliance and measured measurement-gap duration remain separate acceptance checks.

## Dry-run rule

Before formal collection:

1. initialize a disposable dry-run campaign or use a separate dry-run directory;
2. perform one cue sequence for each of the six conditions;
3. verify audio, visual timing, event logging, recorder output and measured gaps;
4. fix software or setup problems before the formal campaign begins;
5. do not mix dry-run data with the 55 formal slots.

## Formal collection rule

Once the formal campaign starts:

- do not edit `campaign_manifest.json`;
- do not edit `randomized_trial_order.csv`;
- do not replace rejected evidence silently;
- preserve the conductor event log even if the trial is rejected;
- update status and rejection reason through an auditable post-trial workflow rather than deleting a slot;
- use the recorded vision stream to calculate actual occlusion duration;
- require actual gaps within the protocol tolerance before acceptance.

## Test

```bash
PYTHONPATH=ghost_sim_ros2:ghost_sim_ros2/tools \
python3 -m pytest -q ghost_sim_ros2/test/test_campaign_operations.py
```

The tests verify:

- deterministic 55-slot randomization;
- complete and unique trial IDs;
- protocol-commit rejection rules;
- non-destructive initialization;
- directory and lock creation;
- cue profiles for all condition classes;
- conductor plan lookup by randomized sequence.
