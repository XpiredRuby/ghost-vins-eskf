# GHOST Physical Validation Master Runbook

## Mission

Execute the remaining physical work in one controlled USB UVC / Raspberry Pi setup while preserving claims, timing, truth, configuration and evidence integrity.

## Session estimate

Reserve **4.5–6 hours** for a full uninterrupted session, plus breaks that do not disturb the setup.

Expected recording work:

| Phase | Planned recordings |
|---|---:|
| Controlled stationary covariance | 1 accepted 90-second run |
| Ground-truth grid | 6 stationary point windows |
| Campaign dry runs | 6, excluded from formal statistics |
| Formal paired campaign | 55 planned accepted/rejected slots |
| Replacement evidence | approximately 5–10 as needed; never silently replaces rejection |
| Runtime/timing blocks | 4–5 representative blocks |
| Public hero demonstration | 3 preserved takes |

## Non-negotiable session rules

- The camera is a standard **USB UVC webcam**, not CSI.
- Camera and AprilTag are rigidly mounted; neither is hand-held.
- Camera controls, calibration, device node, resolution, format and frame rate are recorded.
- The camera does not move between controlled-R and grid phases.
- Any later camera/setup movement creates a new setup block and blocks casual pooling.
- Formal campaign parameters are locked after dry runs and before formal results are observed.
- Chat messages never provide one-/two-/three-second timing; the local conductor does.
- Actual acceptance uses recorded vision gaps and measured physical truth.
- Rejected runs remain preserved with reasons.
- Raw private device inventory is not committed.
- Every major phase is packaged and verified before the setup is dismantled.

## Phase 0 — workspace and privacy preparation

Before powering the physical setup:

1. pull the reviewed `main` branch;
2. confirm a clean or explicitly recorded working tree;
3. create session directories outside the repository;
4. copy the machine-readable session checklist;
5. prepare measuring tape/ruler, rigid mounts, printed tag, opaque occluder and path markers;
6. ensure sufficient disk space;
7. disable notifications or background work that could disturb timing;
8. keep serial numbers, network details and personal documents out of photographs.

Create the live session checklist:

```bash
cp ghost_sim_ros2/docs/PHYSICAL_VALIDATION_SESSION_CHECKLIST.example.json \
  ~/ghost_trials/physical_validation_session.json
```

Validate structure:

```bash
python3 ghost_sim_ros2/analysis/validate_physical_session.py \
  ~/ghost_trials/physical_validation_session.json
```

## Phase 1 — USB hardware inventory and photographs

Run the privacy-separated inventory capture before moving the setup:

```bash
python3 ghost_sim_ros2/tools/capture_usb_hardware_inventory.py \
  --device /dev/video0 \
  --calibration ~/ghost_camera_calibration.json \
  --out-dir ~/ghost_trials/hardware_inventory_$(date -u +%Y%m%d_%H%M%SZ)
```

Capture the ten predeclared photographs from `GHOST_HARDWARE_BOM.md`.

Do not publish anything from `private_raw_do_not_publish`. Review the public tree manually before copying model/mode information into `hardware_bom.json`.

## Phase 2 — rigid setup and coordinate definition

- Fix the USB webcam mount.
- Fix the AprilTag to a rigid carrier.
- Define and photograph the coordinate origin and axes.
- Measure tag size and camera-to-tag standoff.
- Mark six non-collinear grid points with x/y variation.
- Mark formal campaign start, endpoint and maneuver turn point.
- Fix the occluder position or handling method.
- Lock exposure, white balance and focus where supported.
- Record cable routing and strain relief.

Do not proceed until the physical arrangement can remain unchanged through controlled R and grid validation.

## Phase 3 — controlled stationary covariance

Run the hardened helper:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

The helper must finish with:

```text
ACCEPTABLE_FOR_ENGINEER_REVIEW_DOES_NOT_VALIDATE_TRACKER_ACCURACY
```

If rejected, preserve the full directory, diagnose the cause and collect a new separately named run. Do not trim a favorable window or overwrite the failed evidence.

Package and verify the accepted controlled-R directory before the grid phase.

## Phase 4 — six-point ground-truth grid

Use the same camera position and controls.

- Six measured, non-collinear points.
- At least 10 seconds stationary per point.
- No camera contact between points.
- Store the fixed point windows in the required grid CSV.
- Run the existing grid analysis.
- Generate the discrete grid visualization dashboard.
- Package and verify the grid evidence.

The grid result supports setup-specific AprilTag position bias/RMSE, not general production accuracy.

## Phase 5 — six dry runs

Perform one dry run for each formal condition:

1. stationary visible;
2. endpoint no occlusion;
3. endpoint with 1-second requested gap;
4. endpoint with 2-second requested gap;
5. endpoint with 3-second requested gap;
6. maneuver with 2-second requested gap.

Verify:

- recorder and tracker logs;
- visual/audio conductor;
- measured gap extraction;
- endpoint truth workflow;
- trial-state update;
- runtime/timing tools;
- archive packaging.

Dry-run data is never inserted into formal slots.

## Phase 6 — parameter lock and campaign initialization

After dry-run fixes:

- lock camera controls;
- lock formal IMM and MH parameters;
- lock analysis definitions;
- record Git commit;
- initialize the formal campaign and random order;
- store the campaign lock;
- do not tune after formal results are observed.

Initialize:

```bash
python3 ghost_sim_ros2/tools/campaign_operations.py \
  --template ghost_sim_ros2/docs/IMM_MH_CAMPAIGN_MANIFEST.example.json \
  --out ~/ghost_trials/imm_mh_campaign_v1 \
  --resolve-protocol-commit \
  --repo-root .
```

## Phase 7 — formal 55-slot paired campaign

For each randomized sequence:

1. start the live measurement and both trackers;
2. start the trial recorder;
3. start the local conductor for the current sequence;
4. execute only the shown condition;
5. stop recording cleanly;
6. inspect the raw vision gap and required logs;
7. accept or reject through the audited state tool;
8. preserve all evidence;
9. continue to the next randomized slot.

Accepted trials require measured endpoint truth and protocol-compliant gap. Rejections require a reason. Never rerun a failed slot under the same trial ID.

## Phase 8 — representative runtime and USB timing blocks

Collect resource/timing evidence for:

- stationary controlled-R setup;
- no-occlusion motion;
- 3-second occlusion;
- maneuvering occlusion;
- selected hero demonstration.

Record Pi CPU, process CPU/RSS, memory, temperature, load, vision rate, interarrival jitter and receive-latency diagnostics.

## Phase 9 — three hero demonstration takes

Use the separate hero protocol. Preserve all three takes. The chosen take is selected for clarity after all takes are retained and is labeled representative presentation evidence—not the statistical campaign.

Do not use the hero run to replace formal data or infer a confidence interval.

## Phase 10 — analysis and integrity

- finalize campaign state only when no slots remain planned;
- run the audited campaign analyzer;
- generate public visuals;
- generate runtime/timing summaries;
- package the full campaign;
- verify locally;
- copy to a second device;
- verify the copy;
- preserve verification JSON.

## Phase 11 — public release review

Before updating GitHub Pages or resume claims:

- verify sample counts;
- label report-grade versus exploratory conditions;
- include rejected/failure counts;
- preserve hardware-versus-SIL distinction;
- privacy-review photos and inventory;
- avoid full dynamic RMSE claims without independent trajectory truth;
- ensure every public number traces to a committed or archived summary;
- update README, technical report, BOM, career snippets and site together.

## Stop conditions

Stop the session and preserve evidence when:

- camera or mount moves unexpectedly;
- supported controls cannot remain locked;
- tag carrier flexes or detaches;
- coordinate marks move;
- timestamp order is invalid;
- required topics/logs disappear;
- disk/power/temperature becomes unsafe;
- the operator is too fatigued to execute repeatably;
- privacy-sensitive material is at risk of being published.

A cleanly stopped partial session is stronger than a rushed “complete” campaign with questionable evidence.
