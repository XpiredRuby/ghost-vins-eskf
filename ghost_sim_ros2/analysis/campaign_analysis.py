"""Analyze a completed or partially completed GHOST IMM/MH hardware campaign.

The analyzer reads the pinned campaign manifest and raw trial JSONL logs, derives
condition-specific endpoint/reacquisition metrics, produces paired statistics,
and writes recruiter- and engineer-facing plots and reports.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ANALYSIS_STATUS = "HARDWARE_CAMPAIGN_ANALYSIS_REQUIRES_ACCEPTED_TRIALS_AND_MEASURED_ENDPOINT_TRUTH"
CLAIMS_BOUNDARY = "CONDITION_SPECIFIC_RESULTS_ONLY_NO_FULL_DYNAMIC_TRAJECTORY_TRUTH_CLAIM"


def analyze_campaign(campaign_dir: Path, out_dir: Path, *, n_boot: int = 2000, seed: int = 260710) -> dict[str, Any]:
    campaign_dir = campaign_dir.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_json(campaign_dir / "campaign_manifest.json")
    conditions = {str(c["condition_id"]): c for c in manifest.get("conditions", [])}
    trial_results: list[dict[str, Any]] = []
    issues: list[str] = []

    for trial in manifest.get("trials", []):
        if trial.get("status") != "accepted":
            continue
        trial_id = str(trial.get("trial_id", ""))
        condition_id = str(trial.get("condition_id", ""))
        condition = conditions.get(condition_id)
        if not trial_id or condition is None:
            issues.append(f"invalid accepted trial reference: {trial!r}")
            continue
        endpoint = trial.get("endpoint_truth_m")
        if not _valid_endpoint(endpoint):
            issues.append(f"{trial_id}: accepted trial missing finite endpoint_truth_m")
            continue
        trial_path = _resolve_trial_dir(campaign_dir, trial)
        try:
            result = analyze_trial(trial_path, trial, condition)
        except (OSError, ValueError) as exc:
            issues.append(f"{trial_id}: {exc}")
            continue
        trial_results.append(result)
        (trial_path / "trial_metrics.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trial_results:
        by_condition[row["condition_id"]].append(row)

    condition_summaries = [
        summarize_condition(condition_id, condition, by_condition.get(condition_id, []), n_boot=n_boot, seed=seed)
        for condition_id, condition in conditions.items()
    ]

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_status": ANALYSIS_STATUS,
        "claims_boundary": CLAIMS_BOUNDARY,
        "campaign_id": manifest.get("campaign_id"),
        "protocol_commit": manifest.get("protocol_commit"),
        "campaign_dir": str(campaign_dir),
        "accepted_trials_in_manifest": sum(1 for t in manifest.get("trials", []) if t.get("status") == "accepted"),
        "analyzed_trials": len(trial_results),
        "issues": issues,
        "conditions": condition_summaries,
        "trials": trial_results,
        "caveats": [
            "Endpoint truth is physically measured stationary truth, not time-synchronized full-path truth.",
            "Browser cue duration does not replace measured vision-gap duration.",
            "Conditions are analyzed separately and unlike occlusion durations are not pooled into one significance claim.",
            "No superiority claim is valid for a condition below its report-grade accepted-trial threshold.",
        ],
    }
    _write_outputs(summary, out_dir)
    return summary


def analyze_trial(trial_dir: Path, trial: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any]:
    trial_id = str(trial["trial_id"])
    endpoint = trial["endpoint_truth_m"]
    truth = (float(endpoint["x"]), float(endpoint["y"]))
    vision_times = _read_vision_times(_find_file(trial_dir, "vision_pose.jsonl"))
    imm_rows = _read_futures(_find_file(trial_dir, "imm_futures.jsonl"))
    mh_rows = _read_futures(_find_file(trial_dir, "mh_futures.jsonl"))
    if len(vision_times) < 2:
        raise ValueError("vision log contains fewer than two samples")
    if not imm_rows or not mh_rows:
        raise ValueError("IMM or MH futures log contains no usable estimates")

    expected_gap = float(condition.get("target_occlusion_duration_s") or 0.0)
    gap = find_measurement_gap(vision_times, expected_gap)
    imm_metrics = tracker_metrics(imm_rows, truth, gap, expected_gap)
    mh_metrics = tracker_metrics(mh_rows, truth, gap, expected_gap)
    primary_name = "endpoint_prediction_error_m" if expected_gap > 0 else "final_hold_error_m"

    return {
        "trial_id": trial_id,
        "condition_id": str(trial["condition_id"]),
        "repetition": int(trial["repetition"]),
        "status": "accepted",
        "trial_dir": str(trial_dir),
        "endpoint_truth_m": {"x": truth[0], "y": truth[1]},
        "expected_measurement_gap_s": expected_gap,
        "measured_gap": gap,
        "gap_within_protocol_tolerance": (
            True if expected_gap <= 0 else abs(float(gap["duration_s"]) - expected_gap) <= 0.25
        ),
        "primary_metric": primary_name,
        "imm": imm_metrics,
        "mh": mh_metrics,
        "paired_difference_mh_minus_imm_m": _difference(
            mh_metrics.get(primary_name), imm_metrics.get(primary_name)
        ),
    }


def find_measurement_gap(times: list[float], expected_gap_s: float) -> dict[str, Any]:
    ordered = sorted(times)
    gaps = [(ordered[i - 1], ordered[i], ordered[i] - ordered[i - 1]) for i in range(1, len(ordered))]
    nominal = statistics.median([g[2] for g in gaps]) if gaps else 0.0
    if expected_gap_s <= 0.0:
        largest = max(gaps, key=lambda row: row[2])
        return {
            "start_s": None,
            "end_s": None,
            "duration_s": 0.0,
            "largest_inter_sample_gap_s": largest[2],
            "nominal_interval_s": nominal,
            "source": "NO_INTENTIONAL_GAP",
        }
    largest = max(gaps, key=lambda row: row[2])
    return {
        "start_s": largest[0],
        "end_s": largest[1],
        "duration_s": largest[2],
        "largest_inter_sample_gap_s": largest[2],
        "nominal_interval_s": nominal,
        "source": "LARGEST_VISION_INTER_SAMPLE_GAP",
    }


def tracker_metrics(
    rows: list[dict[str, Any]],
    truth: tuple[float, float],
    gap: dict[str, Any],
    expected_gap_s: float,
) -> dict[str, Any]:
    initialized = [row for row in rows if row.get("initialized") and row.get("estimate")]
    if not initialized:
        return _failure_metrics("NO_INITIALIZED_ESTIMATE")

    trajectory = [
        {
            "t_s": row["t_s"],
            "x_m": float(row["estimate"]["x_m"]),
            "y_m": float(row["estimate"]["y_m"]),
            "visible": bool(row.get("visible")),
        }
        for row in initialized
    ]
    final_count = max(1, min(len(initialized), int(round(5.0 / _median_dt(initialized)))))
    final_rows = initialized[-final_count:]
    final_x = statistics.median(float(row["estimate"]["x_m"]) for row in final_rows)
    final_y = statistics.median(float(row["estimate"]["y_m"]) for row in final_rows)
    final_hold_error = math.hypot(final_x - truth[0], final_y - truth[1])

    base = {
        "failure": False,
        "failure_reason": None,
        "final_hold_estimate_m": {"x": final_x, "y": final_y},
        "final_hold_error_m": final_hold_error,
        "endpoint_prediction_error_m": None,
        "first_reacquisition_error_m": None,
        "reacquisition_latency_s": None,
        "max_measurement_age_s": max(
            [float(row["measurement_age_s"]) for row in initialized if row.get("measurement_age_s") is not None]
            or [0.0]
        ),
        "max_covariance_trace_m2": max(
            [_cov_trace(row.get("estimate")) for row in initialized if _cov_trace(row.get("estimate")) is not None]
            or [0.0]
        ),
        "trajectory": trajectory,
    }
    if expected_gap_s <= 0.0:
        return base

    gap_end = float(gap["end_s"])
    hidden = [row for row in initialized if not row.get("visible") and row["t_s"] <= gap_end + 0.25]
    reacquired = [row for row in initialized if row.get("visible") and row["t_s"] >= gap_end - 0.05]
    if not hidden:
        base.update(_failure_metrics("NO_PREDICTION_ONLY_ESTIMATE_BEFORE_REACQUISITION", keep=base))
        return base
    pre = max(hidden, key=lambda row: row["t_s"])
    pre_est = pre["estimate"]
    base["endpoint_prediction_estimate_m"] = {
        "x": float(pre_est["x_m"]),
        "y": float(pre_est["y_m"]),
        "t_s": float(pre["t_s"]),
    }
    base["endpoint_prediction_error_m"] = math.hypot(
        float(pre_est["x_m"]) - truth[0], float(pre_est["y_m"]) - truth[1]
    )
    if not reacquired:
        base.update(_failure_metrics("NO_MEASUREMENT_BACKED_REACQUISITION", keep=base))
        return base
    first = min(reacquired, key=lambda row: row["t_s"])
    first_est = first["estimate"]
    base["first_reacquisition_estimate_m"] = {
        "x": float(first_est["x_m"]),
        "y": float(first_est["y_m"]),
        "t_s": float(first["t_s"]),
    }
    base["first_reacquisition_error_m"] = math.hypot(
        float(first_est["x_m"]) - truth[0], float(first_est["y_m"]) - truth[1]
    )
    base["reacquisition_latency_s"] = max(0.0, float(first["t_s"]) - gap_end)
    return base


def summarize_condition(
    condition_id: str,
    condition: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    n_boot: int,
    seed: int,
) -> dict[str, Any]:
    expected_gap = float(condition.get("target_occlusion_duration_s") or 0.0)
    metric = "endpoint_prediction_error_m" if expected_gap > 0 else "final_hold_error_m"
    valid_pairs = [
        row
        for row in rows
        if not row["imm"].get("failure")
        and not row["mh"].get("failure")
        and _finite(row["imm"].get(metric))
        and _finite(row["mh"].get(metric))
    ]
    imm = [float(row["imm"][metric]) for row in valid_pairs]
    mh = [float(row["mh"][metric]) for row in valid_pairs]
    required = 5 if condition_id == "static_visible" else 8
    paired = paired_summary(imm, mh, n_boot=n_boot, seed=seed) if imm else None
    actual_gaps = [float(row["measured_gap"]["duration_s"]) for row in rows]
    return {
        "condition_id": condition_id,
        "planned_repetitions": int(condition.get("planned_repetitions", 0)),
        "accepted_analyzed": len(rows),
        "valid_paired_metrics": len(valid_pairs),
        "report_grade_minimum": required,
        "report_grade": len(valid_pairs) >= required,
        "primary_metric": metric,
        "expected_measurement_gap_s": expected_gap,
        "measured_gap_median_s": statistics.median(actual_gaps) if actual_gaps else None,
        "gap_tolerance_failures": sum(not row["gap_within_protocol_tolerance"] for row in rows),
        "imm_failures": sum(bool(row["imm"].get("failure")) for row in rows),
        "mh_failures": sum(bool(row["mh"].get("failure")) for row in rows),
        "paired_statistics": paired,
        "interpretation_status": "REPORT_GRADE" if len(valid_pairs) >= required else "EXPLORATORY_OR_PENDING",
    }


def paired_summary(imm: list[float], mh: list[float], *, n_boot: int, seed: int) -> dict[str, Any]:
    if len(imm) != len(mh) or not imm:
        raise ValueError("paired inputs must be equal non-zero length")
    diffs = [m - i for i, m in zip(imm, mh)]
    rng = random.Random(seed)
    boot = []
    for _ in range(n_boot):
        indices = [rng.randrange(len(diffs)) for _ in diffs]
        boot.append(statistics.median(diffs[index] for index in indices))
    boot.sort()
    low = boot[max(0, int(0.025 * len(boot)) - 1)]
    high = boot[min(len(boot) - 1, int(0.975 * len(boot)))]
    wilcoxon = {"available": False, "statistic": None, "p_value": None}
    try:
        from scipy.stats import wilcoxon as scipy_wilcoxon

        if all(abs(value) <= 1e-15 for value in diffs):
            wilcoxon = {"available": True, "statistic": 0.0, "p_value": 1.0}
        else:
            result = scipy_wilcoxon(diffs)
            wilcoxon = {
                "available": True,
                "statistic": float(result.statistic),
                "p_value": float(result.pvalue),
            }
    except (ImportError, ValueError):
        pass
    return {
        "n_trials": len(diffs),
        "imm_median_error_m": statistics.median(imm),
        "mh_median_error_m": statistics.median(mh),
        "median_mh_minus_imm_m": statistics.median(diffs),
        "median_error_reduction_mh_vs_imm_m": statistics.median(imm) - statistics.median(mh),
        "bootstrap_ci_95_mh_minus_imm_m": {"low": low, "high": high, "n_boot": n_boot, "seed": seed},
        "wilcoxon": wilcoxon,
    }


def _write_outputs(summary: dict[str, Any], out_dir: Path) -> None:
    (out_dir / "campaign_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _plot_endpoint_errors(summary, out_dir / "endpoint_error_by_condition.png")
    _plot_paired_differences(summary, out_dir / "paired_difference_by_condition.png")
    _plot_error_vs_gap(summary, out_dir / "error_vs_measurement_gap.png")
    _plot_reacquisition_latency(summary, out_dir / "reacquisition_latency_by_condition.png")
    _plot_failure_rates(summary, out_dir / "failure_rate_by_condition.png")
    _plot_trajectory_overlays(summary, out_dir)
    (out_dir / "campaign_summary.md").write_text(format_markdown(summary), encoding="utf-8")
    (out_dir / "campaign_report.html").write_text(format_html(summary), encoding="utf-8")


def format_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# GHOST IMM/MH Hardware Campaign Summary",
        "",
        f"- Campaign: `{summary.get('campaign_id')}`",
        f"- Analyzed accepted trials: `{summary['analyzed_trials']}`",
        f"- Claims boundary: `{summary['claims_boundary']}`",
        "",
        "| condition | analyzed | valid pairs | grade | metric | IMM median | MH median | MH-IMM median | CI 95% |",
        "|---|---:|---:|---|---|---:|---:|---:|---|",
    ]
    for condition in summary["conditions"]:
        stats = condition.get("paired_statistics")
        if stats:
            ci = stats["bootstrap_ci_95_mh_minus_imm_m"]
            values = (
                f"{stats['imm_median_error_m']:.6g}",
                f"{stats['mh_median_error_m']:.6g}",
                f"{stats['median_mh_minus_imm_m']:.6g}",
                f"[{ci['low']:.6g}, {ci['high']:.6g}]",
            )
        else:
            values = ("NA", "NA", "NA", "NA")
        lines.append(
            f"| `{condition['condition_id']}` | {condition['accepted_analyzed']} | "
            f"{condition['valid_paired_metrics']} | {condition['interpretation_status']} | "
            f"`{condition['primary_metric']}` | {values[0]} | {values[1]} | {values[2]} | {values[3]} |"
        )
    lines.extend(["", "## Issues", ""])
    lines.extend([f"- {item}" for item in summary["issues"]] or ["- None"])
    lines.extend(["", "> Endpoint truth is stationary measured truth; this report does not claim full dynamic trajectory RMSE.", ""])
    return "\n".join(lines)


def format_html(summary: dict[str, Any]) -> str:
    cards = "".join(
        f"<div class='card'><strong>{_html(c['condition_id'])}</strong><span>{c['accepted_analyzed']} analyzed · {c['interpretation_status']}</span></div>"
        for c in summary["conditions"]
    )
    images = [
        ("Endpoint errors", "endpoint_error_by_condition.png"),
        ("Paired differences", "paired_difference_by_condition.png"),
        ("Error versus measurement gap", "error_vs_measurement_gap.png"),
        ("Reacquisition latency", "reacquisition_latency_by_condition.png"),
        ("Failure rates", "failure_rate_by_condition.png"),
    ]
    figures = "".join(
        f"<article><img src='{name}' alt='{_html(title)}'><h2>{_html(title)}</h2></article>"
        for title, name in images
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>GHOST Campaign Results</title><style>body{{margin:0;background:#07111f;color:#f4f8ff;font-family:system-ui,sans-serif}}main{{width:min(1200px,calc(100% - 30px));margin:auto;padding:34px 0}}p,span{{color:#a9bbd3}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card,article{{border:1px solid #29405f;background:#102036;border-radius:14px;padding:16px}}.card strong,.card span{{display:block}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:24px}}img{{width:100%;background:white;border-radius:8px}}.note{{border-left:4px solid #ffb454;padding:14px;background:#201506}}@media(max-width:800px){{.cards,.grid{{grid-template-columns:1fr}}}}</style></head><body><main><h1>GHOST Hardware Campaign Results</h1><p>Campaign {_html(summary.get('campaign_id'))} · {summary['analyzed_trials']} accepted trials analyzed</p><div class='note'>{_html(summary['claims_boundary'])}</div><div class='cards'>{cards}</div><div class='grid'>{figures}</div></main></body></html>"""


def _plot_endpoint_errors(summary: dict[str, Any], path: Path) -> None:
    labels, imm_data, mh_data = [], [], []
    for condition in summary["conditions"]:
        rows = [row for row in summary["trials"] if row["condition_id"] == condition["condition_id"]]
        metric = condition["primary_metric"]
        imm = [row["imm"].get(metric) for row in rows if _finite(row["imm"].get(metric))]
        mh = [row["mh"].get(metric) for row in rows if _finite(row["mh"].get(metric))]
        if imm and mh:
            labels.append(condition["condition_id"])
            imm_data.append(imm)
            mh_data.append(mh)
    fig, ax = plt.subplots(figsize=(max(8, 1.7 * len(labels)), 5.5))
    if labels:
        positions = list(range(1, len(labels) + 1))
        ax.boxplot(imm_data, positions=[p - 0.18 for p in positions], widths=0.3, patch_artist=True)
        ax.boxplot(mh_data, positions=[p + 0.18 for p in positions], widths=0.3, patch_artist=True)
        ax.set_xticks(positions, labels, rotation=25, ha="right")
    ax.set_ylabel("Primary error (m)")
    ax.set_title("Formal IMM and GHOST-MH error by condition")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)



def _boxplot_compat(ax, values, labels, **kwargs):
    try:
        return ax.boxplot(values, tick_labels=labels, **kwargs)
    except TypeError:
        return ax.boxplot(values, labels=labels, **kwargs)

def _plot_paired_differences(summary: dict[str, Any], path: Path) -> None:
    labels, data = [], []
    for condition in summary["conditions"]:
        metric = condition["primary_metric"]
        values = [
            _difference(row["mh"].get(metric), row["imm"].get(metric))
            for row in summary["trials"]
            if row["condition_id"] == condition["condition_id"]
        ]
        values = [value for value in values if _finite(value)]
        if values:
            labels.append(condition["condition_id"]); data.append(values)
    fig, ax = plt.subplots(figsize=(max(8, 1.7 * len(labels)), 5.5))
    if data:
        _boxplot_compat(ax, data, labels)
        ax.tick_params(axis="x", rotation=25)
    ax.axhline(0.0, linewidth=1)
    ax.set_ylabel("MH error - IMM error (m)")
    ax.set_title("Paired tracker error difference by condition")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def _plot_error_vs_gap(summary: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for tracker in ("imm", "mh"):
        xs, ys = [], []
        for row in summary["trials"]:
            value = row[tracker].get("endpoint_prediction_error_m")
            gap = row["measured_gap"].get("duration_s")
            if _finite(value) and _finite(gap) and float(gap) > 0:
                xs.append(float(gap)); ys.append(float(value))
        if xs:
            ax.scatter(xs, ys, label=tracker.upper(), alpha=0.7)
    ax.set_xlabel("Measured vision gap (s)"); ax.set_ylabel("Endpoint prediction error (m)")
    ax.set_title("Prediction error growth versus measured gap"); ax.legend(); ax.grid(True, alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def _plot_reacquisition_latency(summary: dict[str, Any], path: Path) -> None:
    labels, data = [], []
    for condition in summary["conditions"]:
        values = [
            row["imm"].get("reacquisition_latency_s")
            for row in summary["trials"]
            if row["condition_id"] == condition["condition_id"] and _finite(row["imm"].get("reacquisition_latency_s"))
        ]
        if values:
            labels.append(condition["condition_id"]); data.append(values)
    fig, ax = plt.subplots(figsize=(max(8, 1.7 * len(labels)), 5.5))
    if data:
        _boxplot_compat(ax, data, labels); ax.tick_params(axis="x", rotation=25)
    ax.set_ylabel("IMM reacquisition latency (s)"); ax.set_title("Measurement-backed reacquisition latency")
    ax.grid(True, axis="y", alpha=0.3); fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def _plot_failure_rates(summary: dict[str, Any], path: Path) -> None:
    labels, imm_rates, mh_rates = [], [], []
    for condition in summary["conditions"]:
        n = condition["accepted_analyzed"]
        if n:
            labels.append(condition["condition_id"])
            imm_rates.append(condition["imm_failures"] / n)
            mh_rates.append(condition["mh_failures"] / n)
    x = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(max(8, 1.7 * len(labels)), 5.5))
    ax.bar([v - 0.18 for v in x], imm_rates, width=0.36, label="IMM")
    ax.bar([v + 0.18 for v in x], mh_rates, width=0.36, label="MH")
    ax.set_xticks(x, labels, rotation=25, ha="right"); ax.set_ylim(0, 1)
    ax.set_ylabel("Failure fraction"); ax.set_title("Failure/reset fraction by condition"); ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def _plot_trajectory_overlays(summary: dict[str, Any], out_dir: Path) -> None:
    for condition in summary["conditions"]:
        rows = [row for row in summary["trials"] if row["condition_id"] == condition["condition_id"]]
        if not rows:
            continue
        fig, ax = plt.subplots(figsize=(6.5, 6))
        for row in rows:
            for tracker, linestyle in (("imm", "-"), ("mh", "--")):
                trajectory = row[tracker].get("trajectory") or []
                if not trajectory:
                    continue
                x0, y0 = trajectory[0]["x_m"], trajectory[0]["y_m"]
                ax.plot(
                    [point["x_m"] - x0 for point in trajectory],
                    [point["y_m"] - y0 for point in trajectory],
                    linestyle,
                    alpha=0.22,
                )
        ax.set_aspect("equal", adjustable="datalim"); ax.set_xlabel("Relative x (m)"); ax.set_ylabel("Relative y (m)")
        ax.set_title(f"Accepted trajectory overlays: {condition['condition_id']}"); ax.grid(True, alpha=0.3)
        fig.tight_layout(); fig.savefig(out_dir / f"trajectory_overlay_{condition['condition_id']}.png", dpi=180); plt.close(fig)


def _read_vision_times(path: Path) -> list[float]:
    return [float(row["t_rel_s"]) for row in _read_jsonl(path) if _finite(row.get("t_rel_s"))]


def _read_futures(path: Path) -> list[dict[str, Any]]:
    out = []
    for row in _read_jsonl(path):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        estimate = payload.get("estimate")
        if not isinstance(estimate, dict) or not _finite(estimate.get("x_m")) or not _finite(estimate.get("y_m")):
            continue
        t_s = row.get("t_rel_s", payload.get("stamp_s"))
        if not _finite(t_s):
            continue
        out.append(
            {
                "t_s": float(t_s),
                "visible": bool(payload.get("visible")),
                "initialized": bool(payload.get("initialized", True)),
                "measurement_age_s": payload.get("measurement_age_s"),
                "estimate": estimate,
            }
        )
    return sorted(out, key=lambda row: row["t_s"])


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{lineno}: {exc}") from exc
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _resolve_trial_dir(campaign_dir: Path, trial: dict[str, Any]) -> Path:
    path = Path(str(trial.get("trial_dir", "")))
    if not path.is_absolute():
        path = campaign_dir / path
    if not path.exists():
        raise ValueError(f"trial directory does not exist: {path}")
    return path.resolve()


def _find_file(root: Path, filename: str) -> Path:
    direct = root / filename
    if direct.is_file():
        return direct
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {filename} under {root}; found {len(matches)}")
    return matches[0]


def _load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return obj


def _median_dt(rows: list[dict[str, Any]]) -> float:
    dts = [rows[i]["t_s"] - rows[i - 1]["t_s"] for i in range(1, len(rows)) if rows[i]["t_s"] > rows[i - 1]["t_s"]]
    return max(1e-3, statistics.median(dts) if dts else 1.0 / 30.0)


def _cov_trace(estimate: Any) -> float | None:
    if not isinstance(estimate, dict):
        return None
    if _finite(estimate.get("cov_xx")) and _finite(estimate.get("cov_yy")):
        return float(estimate["cov_xx"]) + float(estimate["cov_yy"])
    return None


def _failure_metrics(reason: str, keep: dict[str, Any] | None = None) -> dict[str, Any]:
    out = dict(keep or {})
    out["failure"] = True
    out["failure_reason"] = reason
    out.setdefault("trajectory", [])
    return out


def _valid_endpoint(value: Any) -> bool:
    return isinstance(value, dict) and _finite(value.get("x")) and _finite(value.get("y"))


def _difference(a: Any, b: Any) -> float | None:
    return float(a) - float(b) if _finite(a) and _finite(b) else None


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _html(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a GHOST IMM/MH hardware campaign.")
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=260710)
    args = parser.parse_args(argv)
    summary = analyze_campaign(args.campaign_dir, args.out_dir, n_boot=args.n_boot, seed=args.seed)
    print(f"analyzed_trials={summary['analyzed_trials']}")
    print(f"issues={len(summary['issues'])}")
    print(f"wrote={args.out_dir.expanduser().resolve() / 'campaign_report.html'}")
    return 0 if not summary["issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
