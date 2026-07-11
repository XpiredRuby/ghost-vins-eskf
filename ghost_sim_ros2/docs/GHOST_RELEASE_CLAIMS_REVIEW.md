# GHOST Public Release Claims Review

## Purpose

Maintain a machine-readable map between each README, website, resume or interview claim and the evidence classification that permits or blocks publication.

Template:

```text
ghost_sim_ros2/docs/RELEASE_CLAIMS_MATRIX.example.json
```

## Classifications

| Classification | Meaning | Public use |
|---|---|---|
| `validated` | Direct quantitative evidence supports the exact scoped statement | Allowed with evidence, sample count and limitations |
| `hardware_behavior_only` | Real hardware demonstrates integration/state behavior but not accuracy | Allowed without accuracy language |
| `software_only` | Deterministic simulation/SIL or offline software evidence | Allowed only with software boundary explicit |
| `pending` | Required physical collection or review does not yet exist | Not public-ready |
| `prohibited` | The project scope cannot currently support the statement | Not public-ready |

## Validate the matrix

```bash
python3 ghost_sim_ros2/analysis/validate_release_claims.py \
  ghost_sim_ros2/docs/RELEASE_CLAIMS_MATRIX.example.json
```

The validator enforces:

- unique claim IDs;
- known classifications;
- boolean public readiness;
- evidence and limitation lists;
- no public-ready pending/prohibited claims;
- no placeholders in public-ready statements;
- direct evidence for every promoted statement;
- validated classification for high-risk wording such as flight-ready, production-ready, validated accuracy, centimeter-level, statistically proven or outperforms;
- no accuracy terms inside hardware-behavior-only claims;
- explicit software/SIL wording for software-only claims.

## Final release gate

After physical validation, copy the template into the release evidence directory and replace pending statements only with exact analyzed results.

Then run:

```bash
python3 ghost_sim_ros2/analysis/validate_release_claims.py \
  <release>/release_claims_matrix.json \
  --require-all-resolved \
  --out <release>/release_claims_validation.json
```

`--require-all-resolved` is appropriate only for the chosen final release matrix. It is intentionally not used on the current prevalidation template because several physical claims are honestly pending.

## Promotion workflow

For each pending metric:

1. identify the accepted evidence package and verification result;
2. copy exact sample count, condition and statistic from the machine-readable summary;
3. add evidence paths/hashes;
4. preserve limitations;
5. change classification to `validated` only when the exact claim is supported;
6. set `public_ready: true`;
7. run the validator;
8. update README, website, report and career snippets together;
9. verify that no older contradictory wording remains.

## Examples

Safe hardware behavior:

> The preserved hardware run demonstrates simultaneous formal IMM and GHOST-MH outputs, prediction-only dropout states and reacquisition.

Unsafe before grid/campaign evidence:

> GHOST has validated centimeter-level accuracy and the IMM statistically outperforms MH.

Safe software-only:

> Deterministic SIL connects the formal IMM output to relative-standoff guidance, bounded control, actuator lag and follower dynamics.

Unsafe scope inflation:

> GHOST is flight-ready and production-ready.

## Test

```bash
PYTHONPATH=ghost_sim_ros2:ghost_sim_ros2/tools \
python3 -m pytest -q ghost_sim_ros2/test/test_parameter_claims_lock.py
```

The focused tests cover locked-file changes, overwrite prevention, external labels, pending/prohibited promotion blocks, high-risk wording and final unresolved-claim gating.
