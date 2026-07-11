# GHOST Automated Hardware Campaign Analysis

## Purpose

Turn accepted raw IMM/MH trial directories and measured endpoint truth into condition-specific metrics, paired statistics, trajectory overlays, plots and static reports without manually selecting favorable trials or time windows.

## Evidence boundary

```text
Analysis boundary: CONDITION_SPECIFIC_ENDPOINT_AND_REACQUISITION_METRICS
Not claimed: TIME_SYNCHRONIZED_FULL_DYNAMIC_TRAJECTORY_TRUTH
```

The campaign provides physically measured stationary endpoint truth. It does not provide an independent time-synchronized motion-capture trajectory, so the analyzer does not label its trajectory overlays as full-path RMSE evidence.

## Required accepted-trial inputs

Each accepted manifest trial must contain:

```json
{
  "trial_id": "endpoint_occ_2s_01",
  "condition_id": "endpoint_occ_2s",
  "repetition": 1,
  "status": "accepted",
  "trial_dir": "trial_directories/endpoint_occ_2s_01",
  "endpoint_truth_m": {"x": 1.20, "y": 0.45}
}
```

The trial directory must contain exactly one usable copy of:

```text
vision_pose.jsonl
imm_futures.jsonl
mh_futures.jsonl
```

The analyzer searches nested recorder directories when these files are not directly at the trial root, but it rejects ambiguous multiple matches.

## Derived per-trial metrics

For requested occlusion trials:

- measured vision gap from the largest inter-sample gap;
- gap-versus-target tolerance result;
- formal IMM endpoint prediction error immediately before measurement-backed reacquisition;
- GHOST-MH endpoint prediction error at the corresponding pre-reacquisition state;
- first-reacquisition error;
- reacquisition latency;
- maximum measurement age;
- maximum position covariance trace;
- reset/failure state;
- relative trajectory series for visualization.

For visible/static conditions, the primary metric is the median final-hold error against the measured stationary point.

Each analyzed trial receives:

```text
trial_metrics.json
```

## Condition-specific statistics

The analyzer never pools unlike occlusion durations into one significance test. For each condition it reports:

- accepted analyzed trials;
- valid paired metrics;
- report-grade threshold status;
- IMM and MH median errors;
- median `MH - IMM` paired difference;
- median error reduction;
- fixed-seed bootstrap 95% confidence interval using 2,000 resamples by default;
- Wilcoxon signed-rank result when SciPy is installed;
- gap-tolerance failures;
- IMM and MH failure counts.

The five-trial stationary condition remains a repeatability diagnostic. Other conditions require at least eight valid paired trials for `REPORT_GRADE`; smaller samples are labeled exploratory or pending.

## Run campaign analysis

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/campaign_analysis.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --out-dir ~/ghost_trials/imm_mh_campaign_v1/analysis \
  --n-boot 2000 \
  --seed 260710
```

Expected outputs:

```text
analysis/
├── campaign_summary.json
├── campaign_summary.md
├── campaign_report.html
├── endpoint_error_by_condition.png
├── paired_difference_by_condition.png
├── error_vs_measurement_gap.png
├── reacquisition_latency_by_condition.png
├── failure_rate_by_condition.png
└── trajectory_overlay_<condition>.png
```

## Visual interpretation

- **Endpoint error box plots** show the distribution across accepted repetitions rather than one favorable run.
- **Paired difference plots** use `MH error - IMM error`; values above zero favor the IMM for that metric.
- **Error versus gap** shows whether open-loop prediction error grows with actual measurement-loss duration.
- **Latency plots** expose how quickly a measurement-backed estimate returns.
- **Failure-rate bars** prevent successful-only plots from hiding resets or missed reacquisitions.
- **Trajectory overlays** are start-normalized visual context, not full dynamic truth.

## Ground-truth grid visualization

After the existing grid analysis writes `grid_validation_summary.json`, generate the visual package:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/grid_validation_visuals.py \
  --summary <grid-output>/grid_validation_summary.json \
  --out-dir <grid-output>/visuals
```

Outputs:

```text
visuals/
├── grid_true_vs_measured.png
├── grid_error_vectors.png
├── grid_point_errors.png
├── grid_spatial_error_map.png
├── grid_visuals_summary.json
└── grid_validation_dashboard.html
```

The spatial error map displays only the measured discrete points. It intentionally does not interpolate a smooth heatmap because six points are not enough to claim a continuous accuracy surface.

## Public-site update rule

Real campaign or grid plots may replace placeholders on the public site only after:

1. the relevant trial status is accepted;
2. endpoint/grid coordinates are physically measured and recorded;
3. the manifest and evidence package pass integrity checks;
4. all condition labels and sample counts are visible;
5. exploratory conditions remain labeled exploratory;
6. plots retain the hardware-versus-SIL claims boundary;
7. rejected trials remain counted in failure and quality summaries.

## Test

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 -m pytest -q ghost_sim_ros2/test/test_campaign_analysis_visuals.py
```

The focused fixture tests verify raw JSONL extraction, longest-gap identification, paired bootstrap direction, report generation, all campaign plots, and the four grid-validation visuals.
