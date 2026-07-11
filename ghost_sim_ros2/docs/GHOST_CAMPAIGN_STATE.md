# GHOST Campaign State and Trial Outcome Audit

## Purpose

Record accepted and rejected hardware-trial outcomes without modifying the precollection manifest or randomized order that were hashed before data collection.

## Integrity model

```text
campaign_manifest.json          immutable pinned plan
randomized_trial_order.csv      immutable pinned order
campaign_lock.json              SHA-256 lock for the plan

campaign_state.json             mutable current outcomes
campaign_amendments.jsonl       append-only audit trail
campaign_manifest_effective.json plan + current outcomes for analysis
campaign_validation_current.json current validation result
```

The outcome tool verifies every file listed in `campaign_lock.json` before accepting a state change. A hash mismatch stops the update.

## Accept a trial

Accepted occlusion trials require:

- finite measured endpoint coordinates;
- finite actual vision-gap duration;
- actual gap within ±0.25 seconds of the condition target;
- exactly one usable `vision_pose.jsonl`;
- exactly one usable `imm_futures.jsonl`;
- exactly one usable `mh_futures.jsonl`.

Example:

```bash
python3 ghost_sim_ros2/tools/update_campaign_trial.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --trial-id endpoint_occ_2s_01 \
  --accept \
  --endpoint-x 1.20 \
  --endpoint-y 0.45 \
  --actual-gap-s 2.08 \
  --notes "Clean endpoint hold; no physical disturbance."
```

## Reject a trial

Rejected evidence is preserved. The reason is mandatory:

```bash
python3 ghost_sim_ros2/tools/update_campaign_trial.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --trial-id endpoint_occ_2s_01 \
  --reject "Measured vision gap was outside protocol tolerance" \
  --actual-gap-s 2.41
```

The trial directory is not deleted, renamed or silently replaced.

## Amend an existing outcome

A second update to an accepted or rejected slot requires an explicit audit reason:

```bash
python3 ghost_sim_ros2/tools/update_campaign_trial.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --trial-id endpoint_occ_2s_01 \
  --reject "Camera mount moved during endpoint hold" \
  --amend-reason "Post-trial video review identified physical movement"
```

The append-only audit log retains the prior and updated records.

## Finalize collection

Finalization is blocked while any slot remains `planned`:

```bash
python3 ghost_sim_ros2/tools/update_campaign_trial.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --finalize
```

Successful finalization writes:

```text
campaign_collection_status=COLLECTION_COMPLETE_PENDING_ANALYSIS
```

and validates the effective manifest with `--require-complete` semantics.

## Why the locked manifest remains unchanged

Updating status fields directly inside `campaign_manifest.json` would break its precollection SHA-256 and erase the distinction between what was planned and what happened. Keeping plan and outcome files separate provides:

- reproducible precollection intent;
- auditable deviations;
- explicit rejected-trial retention;
- safe current-state consumption by analysis tools;
- proof that the randomized order was not rewritten after observing results.

## Test

```bash
PYTHONPATH=ghost_sim_ros2:ghost_sim_ros2/tools \
python3 -m pytest -q \
  ghost_sim_ros2/test/test_campaign_operations.py \
  ghost_sim_ros2/test/test_update_campaign_trial.py
```

The tests verify immutable-plan hashes, accepted/rejected validation, endpoint and gap requirements, required raw logs, explicit amendment reasons, retained trial directories and finalization blocking.
