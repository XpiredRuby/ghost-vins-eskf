# GHOST-X Software Verification Report

Release: `ghost-x-software-v1`
Source branch: `ghost-x`
Source commit before generated release documents: `27d1c3286e8da265539a4702030c00513841af29`
G10 result: `PASS` with `47/47` checks passing.

## Phase status

| Phase | Software status | Evidence |
|---|---|---:|
| `G0` | `SOFTWARE_COMPLETE` | 2/2 |
| `G1` | `SOFTWARE_COMPLETE` | 2/2 |
| `G2` | `SOFTWARE_COMPLETE` | 3/3 |
| `G3` | `SOFTWARE_COMPLETE_PHYSICAL_EXECUTION_PENDING` | 2/2 |
| `G4` | `SOFTWARE_COMPLETE_PHYSICAL_EXECUTION_PENDING` | 2/2 |
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

## Open physical verification gates

- G3 range/yaw measurement characterization collection.
- At least 20 paired controlled physical truth trials.
- Physical position/velocity accuracy, reacquisition statistics, and defensible physical NEES.
- Direct hardware reproduction of selected cable, lighting, network, and CPU faults where practical.

## Release decision

The software baseline is releasable as a research and portfolio platform. Physical-performance wording remains gated and is not approved by this report.
