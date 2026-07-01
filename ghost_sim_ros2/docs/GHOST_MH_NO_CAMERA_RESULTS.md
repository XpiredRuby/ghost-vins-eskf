# GHOST-MH No-Camera Results

This document records the first no-camera research benchmark for GHOST-MH. These
results do not require the Raspberry Pi or camera. They evaluate only the
tracking brain using synthetic measurements and known ground truth.

## Why Point RMSE Is Not Enough

The original CV tracker emits one best path. GHOST-MH is intended to emit several
physics-plausible futures during occlusion. Therefore two metrics matter:

1. **Weighted mean point error**: error of the average estimate.
2. **Future-set coverage**: whether one of the carried hypotheses contains the
   true target future.

For an occluded drone, a useful tracker may carry three possible futures:

```text
left turn: 35%
straight: 30%
brake/hover: 20%
right turn: 15%
```

The weighted mean can sit between futures and look worse than a single CV path,
while the future set can still contain the true path. That is why GHOST-MH needs
both point-estimate and multi-future metrics.

## Commands

Point-estimate benchmark:

```bash
cd ghost_sim_ros2
PYTHONPATH=. python3 analysis/ghost_mh_research_benchmark.py
```

Multi-future benchmark:

```bash
cd ghost_sim_ros2
PYTHONPATH=. python3 analysis/ghost_mh_multi_future_benchmark.py
```

## Current Results

The 192-case no-camera suite uses:

- scenarios: `straight`, `turn_left`, `turn_right`, `evasive_brake`
- seeds: `7`, `11`, `19`
- occlusion starts: `5.5`, `7.0`, `8.5`, `9.5` seconds
- occlusion durations: `0.5`, `1.5`, `2.5`, `3.0` seconds

### Point Estimate

```text
cases: 192
mode-bank MH occlusion wins: 81/192
mean mode-bank-vs-cv improvement: -15.53%
```

Interpretation: the weighted mean estimate is not yet a reliable replacement for
the single-model CV point estimate. This is expected for a multi-modal belief:
averaging separated futures can produce a point that lies between plausible
paths.

### Multi-Future Coverage

```text
cases: 192
best future beats CV: 179/192
top-3 future beats CV: 141/192
mean future coverage @ 0.25m: 95.14%
```

Interpretation: the mode-bank tracker is already strong as a multi-future
predictor. It usually carries at least one physically plausible future closer to
truth than the CV path, and its top-3 futures beat CV in most cases.

## Research Status

This is not yet the final graduate result. The next milestone is to turn
multi-future coverage into a usable real-time estimate by adding:

1. probability calibration for top hypotheses,
2. visualization of the top futures,
3. explicit confidence ellipses,
4. reacquisition logic that collapses the future set onto the matching path,
5. hardware validation using AprilTag measurements.
