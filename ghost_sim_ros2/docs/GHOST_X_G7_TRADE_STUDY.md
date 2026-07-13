# GHOST-X G7 Multi-Model and Hypothesis Trade Study

Canonical trials: `24`
IMM candidates: `36`
GHOST-MH candidates: `27`

## Selected synthetic candidates

### Formal IMM

- Parameters: `{"future_horizon_s": 1.5, "maneuver_acceleration_std_mps2": 0.75, "smooth_acceleration_std_mps2": 0.015, "transition_stay_probability": 0.99}`
- Score: `0.389354`
- Position RMSE: `0.0456 m`
- Hidden RMSE: `0.1322 m`
- Future RMSE: `0.1700 m`
- Mean compute: `3927.80 us/step`

### GHOST-MH

- Parameters: `{"future_horizon_s": 1.0, "gate_chi2": 9.21, "max_occlusion_s": 20.0, "model_count": 3, "stationary_prior_scale": 2.0}`
- Score: `1.506977`
- Position RMSE: `0.2248 m`
- Hidden RMSE: `0.6774 m`
- Future RMSE: `0.4681 m`
- Mean compute: `1131.74 us/step`

## Claim boundary

These are synthetic candidate parameters. Hardware measurement characterization and controlled physical truth must confirm or replace them before public physical-performance claims.
