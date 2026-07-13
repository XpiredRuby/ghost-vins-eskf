# GHOST-X G9 DDS and Runtime Report

- RMW: `rmw_fastrtps_cpp`
- QoS scenarios passed: `7/7`
- Real-time claim status: `BENCH_30HZ_DEADLINE_SUPPORTED_NOT_HARD_REAL_TIME_CERTIFICATION`

| Scenario | Pub | Rx | Receive | p99 latency (ms) | Max latency (ms) | Deadline events | Liveliness events | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `best_effort_depth_1` | 11 | 11 | 1.000 | 2330.198 | 2443.067 | 0 | 0 | PASS |
| `best_effort_depth_10_overload` | 4 | 4 | 1.000 | 1853.114 | 1856.307 | 0 | 0 | PASS |
| `reliable_depth_10` | 4 | 4 | 1.000 | 2960.739 | 2993.798 | 0 | 0 | PASS |
| `reliable_depth_100_overload` | 10 | 10 | 1.000 | 1476.165 | 1485.692 | 0 | 0 | PASS |
| `reliable_deadline_liveliness_pause` | 8 | 8 | 1.000 | 2297.205 | 2399.825 | 12 | 11 | PASS |
| `reliable_cpu_stress` | 83 | 82 | 0.988 | 954.899 | 1740.684 | 0 | 0 | PASS |
| `incompatible_best_effort_to_reliable` | 276 | 0 | 0.000 | NA | NA | 0 | 0 | PASS |

## Estimator deadline

30 Hz deadline: `33.333 ms`
All observed maxima below deadline: `True`

## Claim boundary

This is Raspberry Pi bench and loopback DDS evidence. It does not establish operating-system hard-real-time guarantees, bounded network latency in flight, or flight qualification.
