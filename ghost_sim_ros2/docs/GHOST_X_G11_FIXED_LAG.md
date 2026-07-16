# GHOST-X G11 Fixed-Lag Smoother

Selected: `{"acceleration_std_mps2": 0.3, "lag_steps": 20}`
Ablation candidates: `15`

| Set | Baseline RMSE (m) | Fixed-lag RMSE (m) | Baseline hidden (m) | Fixed-lag hidden (m) |
|---|---:|---:|---:|---:|
| Frozen evaluation | 0.0680 | 0.0255 | 0.1989 | 0.0678 |
| OOD | 0.1538 | 0.0452 | 0.3165 | 0.0851 |

## Boundary

The smoother deliberately incurs the reported lag and is evaluated offline. It is not represented as a zero-latency live estimator. The classical causal filter remains available and is the comparison baseline.
