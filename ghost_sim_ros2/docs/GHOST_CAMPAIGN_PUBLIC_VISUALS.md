# GHOST Audited Campaign Runner and Public Visuals

## Purpose

Analyze the immutable precollection plan together with the audited mutable campaign state, then generate clear recruiter-facing visuals without hiding invalid gaps, failures or rejected evidence.

## Recommended analysis command

Use the protocol-aware runner rather than calling the raw core analyzer directly:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/campaign_analysis_runner.py \
  --campaign-dir ~/ghost_trials/imm_mh_campaign_v1 \
  --out-dir ~/ghost_trials/imm_mh_campaign_v1/analysis \
  --n-boot 2000 \
  --seed 260710
```

The runner chooses the analysis manifest in this order:

1. `campaign_manifest_effective.json` when present;
2. immutable `campaign_manifest.json` merged with `campaign_state.json`;
3. immutable plan only when no outcome state exists.

The pinned plan is never rewritten for analysis.

## Protocol filtering

All accepted trials remain visible in quality counts. A trial enters paired statistics only when:

- its measured vision gap passes the predeclared tolerance;
- the formal IMM produces a finite primary metric;
- GHOST-MH produces a finite primary metric;
- neither tracker carries a failure state for the relevant metric.

A trial that was mistakenly marked accepted but fails the raw-log gap check is counted as a gap-tolerance failure and excluded from report-grade paired statistics. It is not silently deleted.

## Gap fields

The runner reports both:

```text
inter_sample_gap_s
estimated_missing_duration_s = inter_sample_gap_s - nominal_vision_interval_s
```

The primary protocol field remains the explicitly labeled inter-sample interval from the last pre-loss vision sample to the first post-loss sample. The estimated missing duration is supplementary context, not a hidden redefinition of the acceptance rule.

## Generate public visuals

After the audited runner finishes:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/campaign_public_visuals.py \
  --summary ~/ghost_trials/imm_mh_campaign_v1/analysis/campaign_summary.json \
  --out-dir ~/ghost_trials/imm_mh_campaign_v1/analysis/public
```

Outputs include:

- `paired_trial_errors.png`: one line per physical trial connecting formal IMM and GHOST-MH errors;
- `tracker_error_distributions.png`: explicit condition-and-estimator labels;
- `representative_<condition>.png`: one median-like accepted example per condition;
- `campaign_public_visuals.json`: generated-file inventory and visual claims boundary.

## Representative-trial rule

The representative trial is selected mechanically:

1. include only protocol-compliant trials with finite IMM and MH primary metrics;
2. calculate the mean of the two tracker errors for each trial;
3. find the median of those mean errors;
4. choose the trial closest to that median;
5. break exact ties by trial ID.

This prevents choosing the visually cleanest or best-performing run after seeing the data.

Required label:

```text
Representative accepted run: median-like example, not best-case performance
```

## Public-site promotion gate

Campaign visuals may be copied into the GitHub Pages site only after:

- the audited state and effective manifest are saved;
- integrity packaging and verification pass;
- sample counts are visible;
- report-grade versus exploratory conditions are explicit;
- failure and gap-tolerance counts remain available;
- representative plots retain their selection rule;
- the hardware-versus-SIL evidence boundary remains visible.

## Test

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 -m pytest -q \
  ghost_sim_ros2/test/test_campaign_analysis_visuals.py \
  ghost_sim_ros2/test/test_campaign_analysis_runner.py
```

The focused tests verify audited-state merging, protocol-gap filtering, supplementary missing-duration reporting, median-like representative selection and generation of clearly labeled public plots.
