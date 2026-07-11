# GHOST Evidence Integrity and Backup

## Purpose

Package controlled-R, grid, campaign or generic GHOST evidence into a non-overwriting ZIP archive with a machine-readable SHA-256 manifest, environment snapshot and independent verification command.

## Boundary

```text
Integrity guarantee: DETECTS_POST_PACKAGE_BYTE_CHANGES
Not guaranteed: PHYSICAL_TRIAL_VALIDITY_OR_CORRECT_EXPERIMENTAL_INTERPRETATION
```

Checksums show whether packaged bytes changed. They do not prove that the camera remained rigid, the endpoint was measured correctly, or the estimator interpretation is scientifically valid. Those requirements remain in the collection protocols and operator attestations.

## Create a controlled-R archive

Write the archive outside the source directory:

```bash
python3 ghost_sim_ros2/tools/evidence_integrity.py package \
  --source ~/ghost_trials/controlled_R_<timestamp> \
  --archive ~/ghost_evidence/controlled_R_<timestamp>.zip \
  --profile controlled_r \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf
```

The `controlled_r` profile requires:

- protocol metadata;
- before/after camera-control evidence;
- camera-control readback table;
- operator attestation;
- raw vision log;
- collection quality summary;
- covariance JSON and Markdown summaries;
- final collection status.

## Create a campaign archive

```bash
python3 ghost_sim_ros2/tools/evidence_integrity.py package \
  --source ~/ghost_trials/imm_mh_campaign_v1 \
  --archive ~/ghost_evidence/imm_mh_campaign_v1.zip \
  --profile campaign \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf
```

The campaign profile requires the pinned manifest, campaign lock, precollection validation, randomized order and trial-directory tree.

## Create a grid archive

After grid analysis:

```bash
python3 ghost_sim_ros2/tools/evidence_integrity.py package \
  --source <grid-output-directory> \
  --archive ~/ghost_evidence/grid_validation_v1.zip \
  --profile grid \
  --repo-root ~/ghost_ws/src/ghost-vins-eskf
```

## Verify an archive

```bash
python3 ghost_sim_ros2/tools/evidence_integrity.py verify \
  --archive ~/ghost_evidence/imm_mh_campaign_v1.zip \
  --out ~/ghost_evidence/imm_mh_campaign_v1_verification.json
```

Verification checks:

- manifest presence;
- manifest SHA-256;
- every listed archived file;
- every listed file size;
- every listed file SHA-256;
- unexpected unlisted evidence members;
- ZIP readability and JSON validity.

## Package contents

Each archive includes:

```text
EVIDENCE_MANIFEST.json
EVIDENCE_MANIFEST.sha256
evidence/<original relative files>
```

The manifest records:

- UTC creation timestamp;
- evidence profile;
- source-directory label;
- file count and total bytes;
- relative paths, sizes and SHA-256 hashes;
- symlink status and target where relevant;
- Python/platform environment;
- Git commit, branch and working-tree status when `--repo-root` is provided;
- missing-artifact list and package completeness status.

## Non-destructive rules

- The tool refuses to overwrite an existing archive.
- The archive must be outside the source directory.
- Required-profile omissions fail packaging by default.
- `--allow-incomplete` is permitted only for diagnostic backups and writes `INCOMPLETE_ALLOWED` plus the exact missing list.
- Do not rename an incomplete package to imply report-grade completeness.
- Preserve the original archive and its verification JSON before copying it to another computer or cloud location.

## Recommended backup sequence

After each major physical phase:

1. stop all recorders cleanly;
2. inspect the final status and missing-artifact report;
3. create the profile-specific archive;
4. verify the archive immediately;
5. copy the archive and verification JSON to a second device;
6. verify the copied archive again;
7. commit only appropriate derived summaries and plots—not private or excessively large raw data—unless the repository evidence policy explicitly allows it.

## Test

```bash
PYTHONPATH=ghost_sim_ros2/tools \
python3 -m pytest -q ghost_sim_ros2/test/test_evidence_integrity.py
```

Focused tests cover complete packaging, missing required files, explicitly incomplete backups, overwrite prevention and deliberate ZIP-member tampering.
