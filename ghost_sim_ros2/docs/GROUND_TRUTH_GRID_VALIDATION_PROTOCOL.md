# Ground Truth Grid Validation Protocol

## Purpose

Estimate AprilTag pose measurement accuracy against measured physical grid points.

One grid trial gives initial accuracy evidence, not full production validation.

## Physical Setup

- Use the same locked camera setup as the controlled `R` protocol.
- Use 5 or 6 measured points.
- Points must not be collinear.
- Include both `x` and `y` variation.
- Define the coordinate origin and photograph or describe it in the trial notes.
- Measure coordinates in meters.
- Do not move the camera between points.

## Collection

- Use the same camera settings as the controlled `R` trial.
- Keep the camera fixed for the full grid trial.
- Place the AprilTag at each measured point.
- Record 10 seconds stationary per point.
- Do not touch or move the camera between points.

## Required Grid CSV Format

```text
point_id,x_true_m,y_true_m,t_start_s,t_end_s
```

Each row defines the analysis window for one physical grid point.

## Analysis Metrics

Report:

- Per-point measured mean `x`/`y`.
- Per-point error `dx`/`dy`.
- Per-point Euclidean error.
- Mean bias.
- RMSE.
- Per-point standard deviation.
- Sample count and sample rate.

## Output

- `grid_validation_summary.md`
- `grid_validation_summary.json`
- Optional plots if existing plotting utilities are available.

## Status

This protocol estimates AprilTag pose measurement accuracy for the measured grid setup. It does not by itself establish full production accuracy, robustness, or generalization to other lighting, tag poses, cameras, or target types.
