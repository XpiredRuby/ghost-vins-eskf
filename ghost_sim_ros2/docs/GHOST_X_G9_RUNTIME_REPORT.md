# GHOST-X G9 DDS and Runtime Report

- RMW: `rmw_fastrtps_cpp`
- QoS scenarios passed: `8/8`
- Real-time claim status: `HARD_REAL_TIME_NOT_CLAIMED_REQUIREMENTS_NOT_MET`

| Scenario | Pub | Rx | Receive | p99 latency (ms) | Max latency (ms) | Deadline events | Liveliness events | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `best_effort_depth_1` | 216 | 216 | 1.000 | 347.905 | 1288.766 | 0 | 0 | PASS |
| `best_effort_depth_10_overload` | 240 | 240 | 1.000 | 310.302 | 463.101 | 0 | 0 | PASS |
| `reliable_depth_10` | 138 | 138 | 1.000 | 365.873 | 1026.332 | 0 | 0 | PASS |
| `reliable_depth_100_overload` | 19 | 19 | 1.000 | 891.531 | 924.363 | 0 | 0 | PASS |
| `reliable_estimator_30hz` | 19 | 19 | 1.000 | 1464.468 | 1544.516 | 0 | 0 | PASS |
| `reliable_deadline_liveliness_pause` | 6 | 6 | 1.000 | 2044.338 | 2081.628 | 8 | 9 | PASS |
| `reliable_cpu_stress` | 123 | 122 | 0.992 | 520.938 | 1213.814 | 0 | 0 | PASS |
| `incompatible_best_effort_to_reliable` | 275 | 0 | 0.000 | NA | NA | 0 | 0 | PASS |

## Predeclared runtime requirements

| Requirement | Result | Evidence summary |
|---|---|---|
| `RT-001` | FAIL | Nominal source-to-receipt latency did not meet the predeclared bounds. |
| `RT-002` | FAIL | The 30 Hz publication/deadline requirement was not met on this bench run. |
| `RT-003` | PASS | Resource and thermal evidence was collected without a reported throttling flag. |

## Estimator deadline

30 Hz deadline: `33.333 ms`
All observed maxima below deadline: `False`

## Claim boundary

This is Raspberry Pi bench and loopback DDS evidence. It does not establish operating-system hard-real-time guarantees, bounded network latency in flight, or flight qualification.
