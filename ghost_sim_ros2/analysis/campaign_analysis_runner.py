"""Run campaign analysis from an immutable plan plus audited mutable state."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from analysis import campaign_analysis as core


def run_audited_analysis(
    campaign_dir: Path,
    out_dir: Path,
    *,
    n_boot: int = 2000,
    seed: int = 260710,
) -> dict[str, Any]:
    root = campaign_dir.expanduser().resolve()
    manifest = load_json(root / "campaign_manifest.json")
    effective_path = root / "campaign_manifest_effective.json"
    state_path = root / "campaign_state.json"

    if effective_path.is_file():
        effective = load_json(effective_path)
        source = "campaign_manifest_effective.json"
    elif state_path.is_file():
        effective = merge_plan_and_state(manifest, load_json(state_path))
        source = "campaign_manifest.json + campaign_state.json"
    else:
        effective = deepcopy(manifest)
        source = "campaign_manifest.json only"

    for trial in effective.get("trials", []):
        path = Path(str(trial.get("trial_dir", "")))
        if not path.is_absolute():
            trial["trial_dir"] = str((root / path).resolve())

    with tempfile.TemporaryDirectory(prefix="ghost_campaign_analysis_") as temp:
        temp_root = Path(temp)
        (temp_root / "campaign_manifest.json").write_text(
            json.dumps(effective, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary = core.analyze_campaign(temp_root, out_dir, n_boot=n_boot, seed=seed)

    summary["source_campaign_dir"] = str(root)
    summary["analysis_manifest_source"] = source
    summary["gap_definition"] = (
        "Measured gap is the inter-sample interval between the last pre-loss and first post-loss "
        "vision sample. Estimated missing duration subtracts the nominal vision interval."
    )
    for trial in summary.get("trials", []):
        gap = trial.get("measured_gap") or {}
        duration = _float_or_none(gap.get("duration_s"))
        nominal = _float_or_none(gap.get("nominal_interval_s"))
        gap["inter_sample_gap_s"] = duration
        gap["estimated_missing_duration_s"] = (
            max(0.0, duration - nominal) if duration is not None and nominal is not None else None
        )
        gap["definition"] = "LAST_PRE_LOSS_TO_FIRST_POST_LOSS_INTER_SAMPLE_INTERVAL"
        trial["measured_gap"] = gap

    summary["conditions"] = protocol_condition_summaries(
        effective,
        summary.get("trials", []),
        n_boot=n_boot,
        seed=seed,
    )
    summary.setdefault("caveats", []).append(
        "Trials marked accepted but failing the predeclared measurement-gap tolerance remain visible "
        "in quality counts and are excluded from paired report-grade statistics."
    )
    core._write_outputs(summary, out_dir.expanduser().resolve())
    return summary


def protocol_condition_summaries(
    manifest: dict[str, Any],
    trials: list[dict[str, Any]],
    *,
    n_boot: int,
    seed: int,
) -> list[dict[str, Any]]:
    out = []
    for condition in manifest.get("conditions", []):
        condition_id = str(condition["condition_id"])
        expected_gap = float(condition.get("target_occlusion_duration_s") or 0.0)
        metric = "endpoint_prediction_error_m" if expected_gap > 0.0 else "final_hold_error_m"
        rows = [trial for trial in trials if trial.get("condition_id") == condition_id]
        compliant = [
            row
            for row in rows
            if row.get("gap_within_protocol_tolerance") is True
            and not row.get("imm", {}).get("failure")
            and not row.get("mh", {}).get("failure")
            and _finite(row.get("imm", {}).get(metric))
            and _finite(row.get("mh", {}).get(metric))
        ]
        imm = [float(row["imm"][metric]) for row in compliant]
        mh = [float(row["mh"][metric]) for row in compliant]
        required = 5 if condition_id == "static_visible" else 8
        actual_gaps = [
            float(row["measured_gap"]["duration_s"])
            for row in rows
            if _finite(row.get("measured_gap", {}).get("duration_s"))
        ]
        out.append(
            {
                "condition_id": condition_id,
                "planned_repetitions": int(condition.get("planned_repetitions", 0)),
                "accepted_analyzed": len(rows),
                "protocol_compliant_valid_pairs": len(compliant),
                "valid_paired_metrics": len(compliant),
                "report_grade_minimum": required,
                "report_grade": len(compliant) >= required,
                "primary_metric": metric,
                "expected_measurement_gap_s": expected_gap,
                "measured_gap_median_s": statistics.median(actual_gaps) if actual_gaps else None,
                "gap_tolerance_failures": sum(
                    row.get("gap_within_protocol_tolerance") is not True for row in rows
                ),
                "imm_failures": sum(bool(row.get("imm", {}).get("failure")) for row in rows),
                "mh_failures": sum(bool(row.get("mh", {}).get("failure")) for row in rows),
                "paired_statistics": (
                    core.paired_summary(imm, mh, n_boot=n_boot, seed=seed) if imm else None
                ),
                "interpretation_status": (
                    "REPORT_GRADE" if len(compliant) >= required else "EXPLORATORY_OR_PENDING"
                ),
                "protocol_filter": (
                    "Only gap-tolerance-compliant trials with finite paired metrics and no tracker "
                    "failure enter paired statistics."
                ),
            }
        )
    return out


def merge_plan_and_state(manifest: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("campaign_id") != state.get("campaign_id"):
        raise ValueError("campaign manifest and state campaign_id do not match")
    outcomes = {str(item["trial_id"]): item for item in state.get("trials", [])}
    effective = deepcopy(manifest)
    for trial in effective.get("trials", []):
        outcome = outcomes.get(str(trial.get("trial_id")))
        if outcome is None:
            continue
        trial.update(
            {
                "status": outcome.get("status", "planned"),
                "endpoint_truth_m": outcome.get("endpoint_truth_m"),
                "rejection_reason": outcome.get("rejection_reason"),
                "actual_measurement_gap_s": outcome.get("actual_measurement_gap_s"),
                "gap_tolerance_status": outcome.get("gap_tolerance_status"),
                "collection_notes": outcome.get("operator_notes", ""),
            }
        )
    effective["campaign_collection_status"] = state.get("campaign_collection_status")
    effective["pinned_manifest_sha256"] = state.get("pinned_manifest_sha256")
    return effective


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _finite(value: Any) -> bool:
    return _float_or_none(value) is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run GHOST campaign analysis from the pinned plan and audited campaign state."
    )
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=260710)
    args = parser.parse_args(argv)
    summary = run_audited_analysis(
        args.campaign_dir,
        args.out_dir,
        n_boot=args.n_boot,
        seed=args.seed,
    )
    print(f"analysis_manifest_source={summary['analysis_manifest_source']}")
    print(f"analyzed_trials={summary['analyzed_trials']}")
    print(f"issues={len(summary['issues'])}")
    return 0 if not summary["issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
