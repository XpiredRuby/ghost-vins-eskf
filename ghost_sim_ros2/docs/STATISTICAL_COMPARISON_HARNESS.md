# Statistical Comparison Harness

`analysis/statistical_comparison.py` provides paired IMM/MH trial comparison for validation summaries.

Use paired inputs only: each IMM error and MH error must come from the same trial, point, or matched condition instance.

## Reported Fields

- `condition`
- `n_trials`
- `median_imm_error`
- `median_mh_error`
- `median_error_difference_mh_minus_imm`
- `median_error_reduction_mh_vs_imm`
- `bootstrap_ci_95_mh_minus_imm`
- `wilcoxon_available`
- `wilcoxon_statistic`
- `wilcoxon_p_value`

Negative `median_error_difference_mh_minus_imm` means MH had lower paired error than IMM. Positive `median_error_reduction_mh_vs_imm` means MH reduced median error relative to IMM.

## SciPy Handling

If SciPy is installed, the harness reports a Wilcoxon signed-rank statistic and p-value. If SciPy is unavailable, it sets `wilcoxon_available` to `false` and still reports the deterministic bootstrap confidence interval.

## Example

```bash
cd ~/ghost_ws/src/ghost-vins-eskf/ghost_sim_ros2
python3 analysis/statistical_comparison.py \
  --condition grid_trial_01 \
  --imm-errors 0.10,0.12,0.09,0.11 \
  --mh-errors 0.08,0.09,0.07,0.10 \
  --out /tmp/grid_trial_01_stats.json
```

This is a statistical summary helper. It does not create accuracy evidence unless the input errors come from a valid ground-truth protocol.
