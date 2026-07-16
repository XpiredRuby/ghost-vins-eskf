# GHOST-X Software Verification Report

Release: `ghost-x-v1.0.0`
Source branch: `main`
Source commit before generated release documents: `9569765bf7c3d5213ca79f57fb0810896cd848fe`
G10 result: `PASS` with `47/47` checks passing.

## Phase status

| Phase | Software status | Evidence |
|---|---|---:|
| `G0` | `SOFTWARE_COMPLETE` | 2/2 |
| `G1` | `SOFTWARE_COMPLETE` | 2/2 |
| `G2` | `SOFTWARE_COMPLETE` | 3/3 |
| `G3` | `SOFTWARE_COMPLETE_GUIDED_HARDWARE_EVIDENCE_FORMAL_CAMPAIGN_PENDING` | 4/4 |
| `G4` | `SOFTWARE_COMPLETE_GUIDED_HARDWARE_EVIDENCE_FORMAL_CAMPAIGN_PENDING` | 4/4 |
| `G5` | `SOFTWARE_COMPLETE` | 3/3 |
| `G6` | `SOFTWARE_COMPLETE` | 2/2 |
| `G7` | `SOFTWARE_COMPLETE` | 2/2 |
| `G8` | `SOFTWARE_COMPLETE` | 2/2 |
| `G9` | `SOFTWARE_COMPLETE` | 2/2 |
| `G10` | `SOFTWARE_COMPLETE` | 3/3 |
| `G11` | `SOFTWARE_COMPLETE` | 2/2 |
| `G12` | `SOFTWARE_COMPLETE` | 4/4 |

## Verification highlights

- 24 deterministic controlled-truth software trials spanning eight scenario families and identical estimator inputs.
- Eigen-based C++ CV, IMM, and multi-hypothesis estimators with unit/property tests, sanitizer execution, deterministic configuration, and Python equivalence.
- Formal NIS/NEES validity labeling, residual diagnostics, covariance sensitivity, and explicit invalid-statistic handling.
- Predeclared IMM and hypothesis-bank trade studies with frozen selection rules.
- Twelve reproducible fault types with detection, isolation/status, recovery, discrepancy, and retained JSONL evidence.
- Raspberry Pi ROS 2 QoS, execution-time, CPU, memory, temperature, throttling, and stress evidence.
- Deterministic replay hashes, stored acceptance bands, deliberate negative-regression self-tests, and GitHub CI workflow.
- Fixed-lag RTS smoothing ablation with frozen evaluation and out-of-distribution testing while retaining the classical causal baseline.
- Browser-guided Raspberry Pi AprilTag trials validating directional lateral/range response and bounded short-dropout reacquisition with machine-readable evidence and explicit claim limits.

## Unvalidated expansion gates

- Formal metrology-backed G3 range/yaw characterization.
- At least 20 paired controlled physical-truth trials for statistical comparison.
- Absolute physical position/velocity accuracy and defensible physical NEES.
- Direct hardware reproduction of selected cable, lighting, network, and CPU faults where practical.

## Release decision

The software plus guided hardware-validation baseline is releasable as a research and portfolio platform. Absolute-accuracy, universal-superiority, hard-real-time, and flight-qualification wording remains prohibited.
