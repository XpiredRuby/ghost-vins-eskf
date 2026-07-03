# GHOST Statistics Harness Runbook

This software-only tool summarizes benchmark CSV metrics into grouped mean, sample standard deviation, standard error, and 95% confidence intervals.

It does not require the Raspberry Pi, camera, AprilTag, or ROS runtime.

## Why This Exists

GHOST needs repeatable evidence, not single-run anecdotes. The stats harness converts benchmark outputs into aggregate tables that can support research claims and expose uncertainty.

Use it for:

- no-camera CV/IMM/MH benchmark CSVs,
- measurement covariance trials,
- CRLB sweeps,
- future camera validation logs,
- scenario-specific failure analysis.

## Run

From the repository root:

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/stats_harness.py \
  --csv ~/ghost_logs/benchmark.csv \
  --metrics rmse_m,coverage_frac \
  --group-by scenario
```

For a CSV output instead of Markdown:

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/stats_harness.py \
  --csv ~/ghost_logs/benchmark.csv \
  --metrics rmse_m,coverage_frac \
  --group-by scenario \
  --out ~/ghost_logs/benchmark_summary.csv
```

## Output Fields

Each summary row contains:

- group key,
- metric name,
- sample count,
- mean,
- sample standard deviation,
- standard error,
- approximate 95% confidence interval.

The 95% interval uses the normal approximation:

```text
mean +/- 1.96 * stderr
```

## Interpretation

This tool is a statistical summary layer. It does not decide whether a tracker is correct. It makes claims more honest by showing sample count and uncertainty.

For small sample counts, the 95% CI is only a rough reference. For final research reporting, use enough trials per scenario and consider scenario-stratified summaries.

## Current Tests

CI verifies that:

- mean/std/stderr/CI calculations are correct for simple inputs,
- grouping by scenario works,
- missing and non-finite values are ignored,
- summary CSV output is written,
- Markdown output contains the expected metric table.
