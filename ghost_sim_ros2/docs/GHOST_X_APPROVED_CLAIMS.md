# GHOST-X Approved and Prohibited Claims

## Approved software and qualified bench claims

### CLM-SW-001

Built a ROS 2 Raspberry Pi tracking and autonomy platform with formal IMM, multi-hypothesis tracking, deterministic replay, and machine-readable evidence contracts.

**Qualification:** Platform claim; not a flight-qualified system.

**Requirements:** `EST-001`, `EST-002`, `SYS-003`, `DAT-001`, `DAT-002`

**Tests:** `T-IMM-001`, `T-MH-001`, `T-SCHEMA-001`, `T-FRAME-001`, `T-TIME-001`

**Evidence:** `GHOST_X_G2_VALIDATION.json`, `GHOST_X_G10_CI_REPORT.json`

### CLM-SW-002

Implemented an Eigen-based C++ estimator library and matched C++ and Python outputs across 24 frozen synthetic trials within declared numerical tolerances.

**Qualification:** Numerical equivalence on pinned vectors, not independent physical accuracy.

**Requirements:** `EST-004`, `EST-005`, `EST-006`, `SW-001`, `SW-002`

**Tests:** `T-DET-001`, `T-COV-001`, `T-EQUIV-001`, `T-CPP-001`, `T-ASSURE-001`

**Evidence:** `GHOST_X_G5_VALIDATION.json`, `GHOST_X_G5_EQUIVALENCE.json`

### CLM-SW-003

Executed a 24-trial deterministic controlled-truth software campaign across eight motion and visibility-loss families using identical estimator inputs.

**Qualification:** Synthetic analytic truth; controlled physical truth remains pending.

**Requirements:** `SYS-001`, `EST-003`, `VNV-001`

**Tests:** `T-PAIR-001`, `T-BASE-001`, `T-TRUTH-001`

**Evidence:** `GHOST_X_G4_VALIDATION.json`, `GHOST_X_G10_CI_REPORT.json`

### CLM-SW-004

Implemented and verified detection, isolation, status, recovery, and retained evidence for 12 reproducible software-injected faults.

**Qualification:** Deterministic software injection; selected faults still require direct hardware/runtime reproduction.

**Requirements:** `DAT-004`, `VNV-006`, `FDIR-001`, `FDIR-002`

**Tests:** `T-DATAFAULT-001`, `T-FALSE-001`, `T-FAULT-001`, `T-FAULTTIME-001`

**Evidence:** `GHOST_X_G8_FAULT_REPORT.json`

### CLM-SW-005

Benchmarked ROS 2 QoS behavior, estimator execution, CPU, memory, temperature, and throttling on a Raspberry Pi using 8 declared runtime scenarios.

**Qualification:** HARD_REAL_TIME_NOT_CLAIMED_REQUIREMENTS_NOT_MET

**Requirements:** `RT-001`, `RT-002`, `RT-003`

**Tests:** `T-LATENCY-001`, `T-JITTER-001`, `T-RESOURCE-001`

**Evidence:** `GHOST_X_G9_RUNTIME_REPORT.json`

### CLM-SW-006

Added one-command deterministic regression gates with 47 requirements and evidence checks plus CI artifact export.

**Qualification:** Synthetic and stored-evidence regression protection; physical campaign data will be added after collection.

**Requirements:** `REP-001`, `REP-002`, `CLM-001`

**Tests:** `T-REPLAY-001`, `T-CI-001`, `T-CLAIM-001`

**Evidence:** `GHOST_X_G10_CI_REPORT.json`, `.github/workflows/ghost-x-regression.yml`

## Prohibited or pending claims

- **CLM-PENDING-001:** Hardware-validated room-scale position or velocity accuracy across the formal campaign. — G3 measurement collection and at least 20 paired controlled physical trials are not complete. (requirements: VNV-002, VNV-003, VNV-004, VNV-005; tests: T-CAMPAIGN-001, T-ACCURACY-001, T-VELOCITY-001, T-REACQ-001)
- **CLM-PENDING-002:** GHOST-MH statistically outperforms formal IMM. — No physical paired statistics support this claim, and frozen synthetic results do not justify a universal superiority statement. (requirements: SYS-001, VNV-002, VNV-003, VNV-004; tests: T-PAIR-001, T-CAMPAIGN-001, T-ACCURACY-001, T-VELOCITY-001)
- **CLM-PENDING-003:** Hard-real-time, flight-qualified, or safety-certified operation. — Bench timing and resource evidence does not establish operating-system hard-real-time bounds or certification; RT-001 and RT-002 did not meet their predeclared bench limits in the final run. (requirements: RT-001, RT-002, RT-003; tests: T-LATENCY-001, T-JITTER-001, T-RESOURCE-001)
- **CLM-PENDING-004:** Autonomous flight with VIO, SLAM, PX4, or independent observer-pose estimation. — The mission simulation assumes a known local observer pose and map. (requirements: SYS-002, DAT-001; tests: T-MODE-001, T-FRAME-001)
