"""Generate clear public-facing plots from campaign_summary.json."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def generate_public_visuals(summary_path: Path, out_dir: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("campaign summary root must be an object")
    out = out_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)

    generated = []
    paired_path = out / "paired_trial_errors.png"
    _paired_trial_plot(summary, paired_path)
    generated.append(paired_path.name)

    distribution_path = out / "tracker_error_distributions.png"
    _distribution_plot(summary, distribution_path)
    generated.append(distribution_path.name)

    for condition in summary.get("conditions", []):
        representative = choose_representative(summary, condition)
        if representative is None:
            continue
        path = out / f"representative_{condition['condition_id']}.png"
        _representative_plot(representative, condition, path)
        generated.append(path.name)

    report = {
        "source_summary": str(summary_path.expanduser()),
        "generated_files": generated,
        "visual_boundary": (
            "REPRESENTATIVE_RUNS_ARE_MEDIAN_LIKE_ACCEPTED_EXAMPLES_NOT_PROOF_OF_BEST_OR_WORST_CASE"
        ),
    }
    (out / "campaign_public_visuals.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def choose_representative(summary: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any] | None:
    metric = condition.get("primary_metric")
    rows = [
        trial
        for trial in summary.get("trials", [])
        if trial.get("condition_id") == condition.get("condition_id")
        and trial.get("gap_within_protocol_tolerance") is True
        and _finite(trial.get("imm", {}).get(metric))
        and _finite(trial.get("mh", {}).get(metric))
    ]
    if not rows:
        return None
    scores = [
        (float(row["imm"][metric]) + float(row["mh"][metric])) / 2.0 for row in rows
    ]
    target = statistics.median(scores)
    index = min(range(len(rows)), key=lambda i: (abs(scores[i] - target), rows[i]["trial_id"]))
    return rows[index]


def _paired_trial_plot(summary: dict[str, Any], path: Path) -> None:
    conditions = [
        condition
        for condition in summary.get("conditions", [])
        if condition.get("paired_statistics")
    ]
    fig, axes = plt.subplots(
        max(1, len(conditions)),
        1,
        figsize=(8.5, max(4.5, 3.5 * len(conditions))),
        squeeze=False,
    )
    for ax, condition in zip(axes[:, 0], conditions):
        metric = condition["primary_metric"]
        rows = [
            trial
            for trial in summary.get("trials", [])
            if trial.get("condition_id") == condition["condition_id"]
            and trial.get("gap_within_protocol_tolerance") is True
            and _finite(trial.get("imm", {}).get(metric))
            and _finite(trial.get("mh", {}).get(metric))
        ]
        for index, row in enumerate(rows, start=1):
            imm = float(row["imm"][metric])
            mh = float(row["mh"][metric])
            ax.plot([0, 1], [imm, mh], marker="o", alpha=0.65)
            ax.annotate(str(index), (1.02, mh), fontsize=8)
        ax.set_xticks([0, 1], ["Formal IMM", "GHOST-MH"])
        ax.set_ylabel("Error (m)")
        ax.set_title(
            f"{condition['condition_id']} · {len(rows)} protocol-compliant paired trials"
        )
        ax.grid(True, axis="y", alpha=0.3)
    if not conditions:
        axes[0, 0].text(0.5, 0.5, "No paired campaign results available", ha="center", va="center")
        axes[0, 0].set_axis_off()
    fig.suptitle("Paired trial errors: each line is the same physical trial", y=1.005)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _distribution_plot(summary: dict[str, Any], path: Path) -> None:
    labels, values = [], []
    for condition in summary.get("conditions", []):
        metric = condition.get("primary_metric")
        rows = [
            trial
            for trial in summary.get("trials", [])
            if trial.get("condition_id") == condition.get("condition_id")
            and trial.get("gap_within_protocol_tolerance") is True
        ]
        for tracker, display in (("imm", "IMM"), ("mh", "MH")):
            data = [
                float(row[tracker][metric])
                for row in rows
                if _finite(row.get(tracker, {}).get(metric))
            ]
            if data:
                labels.append(f"{condition['condition_id']}\n{display}")
                values.append(data)
    fig, ax = plt.subplots(figsize=(max(9, 1.1 * len(labels)), 5.8))
    if values:
        ax.boxplot(values, tick_labels=labels, showmeans=True)
        ax.tick_params(axis="x", rotation=35)
    else:
        ax.text(0.5, 0.5, "No protocol-compliant distributions available", ha="center", va="center")
    ax.set_ylabel("Condition primary error (m)")
    ax.set_title("Tracker error distributions with explicit estimator labels")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _representative_plot(
    trial: dict[str, Any], condition: dict[str, Any], path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    for key, label, linestyle in (
        ("imm", "Formal IMM", "-"),
        ("mh", "GHOST-MH", "--"),
    ):
        trajectory = trial.get(key, {}).get("trajectory") or []
        if not trajectory:
            continue
        ax.plot(
            [point["x_m"] for point in trajectory],
            [point["y_m"] for point in trajectory],
            linestyle=linestyle,
            linewidth=2,
            label=label,
        )
        hidden = [point for point in trajectory if not point.get("visible")]
        if hidden:
            ax.scatter(
                [point["x_m"] for point in hidden],
                [point["y_m"] for point in hidden],
                s=12,
                alpha=0.5,
            )
    truth = trial.get("endpoint_truth_m") or {}
    if _finite(truth.get("x")) and _finite(truth.get("y")):
        ax.scatter([truth["x"]], [truth["y"]], marker="*", s=180, label="Measured endpoint truth")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(
        f"Representative accepted run: {condition['condition_id']}\n"
        f"{trial['trial_id']} · measured gap {trial['measured_gap']['duration_s']:.3f} s"
    )
    ax.grid(True, alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    handles.append(Line2D([0], [0], marker="o", linestyle="None", alpha=0.5))
    labels.append("Prediction-only samples")
    ax.legend(handles, labels)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate unambiguous public plots from a GHOST campaign summary."
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = generate_public_visuals(args.summary, args.out_dir)
    print(f"generated={len(report['generated_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
