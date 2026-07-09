#!/usr/bin/env python3
"""Create final stationary-noise JSON/Markdown artifacts from t,x,y,z CSV."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from analysis.measurement_covariance import estimate_empirical_stationary_r
from analysis.stationary_noise_analysis import analyze_pose_csv, format_markdown_report, report_to_dict

RAW_R_STATUS = "RECOMMENDED_EMPIRICAL_RAW_R_XY_CANDIDATE_PENDING_ENGINEER_REVIEW"
DETRENDED_R_STATUS = "DIAGNOSTIC_ONLY_NOT_DEFAULT_FILTER_R"
WHITE_NOISE_CAVEAT = (
    "Empirical raw R may include colored/drift components. This artifact does not prove white noise, "
    "does not validate estimator accuracy, and must be reviewed with autocorrelation, PSD, and Allan diagnostics."
)


def _json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


def build_summary(csv_path: Path, include_detrended_r: bool = False) -> dict:
    report = analyze_pose_csv(csv_path)
    raw_r = estimate_empirical_stationary_r(csv_path, sample_mode="raw", dimensions=("x", "y"))
    out = {
        "source_csv": str(csv_path),
        "status_labels": {
            "recommended_raw_r_status": RAW_R_STATUS,
            "detrended_r_status": DETRENDED_R_STATUS if include_detrended_r else "NOT_REQUESTED",
            "white_noise_caveat": "RAW_R_MAY_INCLUDE_COLORED_OR_DRIFT_COMPONENTS",
            "estimator_accuracy_status": "DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY",
        },
        "caveats": [
            WHITE_NOISE_CAVEAT,
            "Use empirical raw R_xy as the candidate measurement covariance only after camera controls are locked and read back before/after the trial.",
            "Detrended R, when included, is diagnostic-only and must not replace raw R without a stated modeling decision.",
        ],
        "noise_analysis_report": report_to_dict(report),
        "empirical_raw_r": raw_r.to_dict(),
    }
    if include_detrended_r:
        out["detrended_diagnostic_r"] = estimate_empirical_stationary_r(
            csv_path, sample_mode="detrended", dimensions=("x", "y")
        ).to_dict()
    return _json_safe(out)


def build_markdown(summary: dict) -> str:
    report_md = format_markdown_report(analyze_pose_csv(summary["source_csv"]))
    raw = summary["empirical_raw_r"]
    lines = [report_md.rstrip(), "", "## Recommended empirical raw R_xy", ""]
    lines.extend(
        [
            f"Source CSV: `{summary['source_csv']}`",
            f"Status: `{summary['status_labels']['recommended_raw_r_status']}`",
            f"Estimator: `{raw['estimator']}`",
            f"Dimensions: `{','.join(raw['dimensions'])}`",
            f"Sample mode: `{raw['sample_mode']}`",
            f"Sample count: `{raw['sample_count']}`",
            "",
            "| row | x | y |",
            "| --- | ---: | ---: |",
        ]
    )
    for name, row in zip(raw["dimensions"], raw["covariance"]):
        lines.append(f"| {name} | " + " | ".join(f"`{v:.12g}`" for v in row) + " |")
    lines.extend(
        [
            "",
            f"Assumption label: `{raw['assumption_label']}`",
            f"Provenance: {raw['provenance']}",
            "",
            "> Caveat: raw R may include colored/drift components and is not proof of white noise. "
            "Review raw autocorrelation, PSD, and Allan deviation diagnostics before using this as final filter R.",
            "",
        ]
    )
    det = summary.get("detrended_diagnostic_r")
    if det is not None:
        lines.extend(
            [
                "## Detrended diagnostic R_xy",
                "",
                f"Status: `{summary['status_labels']['detrended_r_status']}`",
                "This matrix is diagnostic-only and is not the default recommended filter R.",
                "",
                "| row | x | y |",
                "| --- | ---: | ---: |",
            ]
        )
        for name, row in zip(det["dimensions"], det["covariance"]):
            lines.append(f"| {name} | " + " | ".join(f"`{v:.12g}`" for v in row) + " |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_summary(csv_path: Path, json_out: Path, md_out: Path, include_detrended_r: bool = False) -> dict:
    summary = build_summary(csv_path.expanduser(), include_detrended_r=include_detrended_r)
    json_out = json_out.expanduser()
    md_out = md_out.expanduser()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    md_out.write_text(build_markdown(summary), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create stationary noise summary artifacts from t,x,y,z CSV.")
    parser.add_argument("--csv", required=True, type=Path, help="Input CSV with schema t,x,y,z")
    parser.add_argument("--json-out", required=True, type=Path, help="Output noise_summary.json path")
    parser.add_argument("--md-out", required=True, type=Path, help="Output noise_summary.md path")
    parser.add_argument("--include-detrended-r", action="store_true", help="Also include detrended diagnostic R")
    args = parser.parse_args(argv)

    summary = write_summary(args.csv, args.json_out, args.md_out, include_detrended_r=args.include_detrended_r)
    raw = summary["empirical_raw_r"]
    print(f"source_csv: {summary['source_csv']}")
    print(f"raw_r_samples: {raw['sample_count']}")
    print(f"wrote_json: {args.json_out.expanduser()}")
    print(f"wrote_md: {args.md_out.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
