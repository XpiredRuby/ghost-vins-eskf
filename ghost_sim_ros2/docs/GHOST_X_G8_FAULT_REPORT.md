# GHOST-X G8 Fault-Injection Report

Faults: `12`
Passed: `12`
Overall: `PASS`

| Fault | Detection | Isolation | Recovery (s) | Result |
|---|---|---|---:|---|
| `camera_disconnect` | True | True | 1.400 | PASS |
| `frozen_measurement` | True | True | 1.400 | PASS |
| `duplicate_measurement` | True | True | 1.400 | PASS |
| `false_detection` | True | True | 1.200 | PASS |
| `covariance_corruption` | True | True | 1.200 | PASS |
| `latency` | True | True | 1.400 | PASS |
| `out_of_sequence_data` | True | True | 1.400 | PASS |
| `node_restart` | True | True | 1.200 | PASS |
| `cpu_saturation` | True | True | 1.200 | PASS |
| `network_degradation` | True | True | 1.200 | PASS |
| `parameter_mismatch` | True | True | 1.400 | PASS |
| `lighting_degradation` | True | True | 1.400 | PASS |

## Boundary

This campaign verifies deterministic software monitors, status propagation, isolation gates, recovery logic, and retained evidence. Actual cable disconnects, DDS impairment, CPU stress, and lighting tests remain separate hardware/runtime evidence.
