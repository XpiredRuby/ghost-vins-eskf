"""Quality gate for a predeclared GHOST controlled-R collection."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACCEPTABLE = "ACCEPTABLE_FOR_FIXED_WINDOW_ANALYSIS"
REJECT = "REJECT_CONTROLLED_R_COLLECTION"
ACCURACY_BOUNDARY = "DOES_NOT_VALIDATE_TRACKER_ACCURACY"


@dataclass(frozen=True)
class PoseSample:
    t_s: float
    x_m: float
    y_m: float
    z_m: float


def load_vision_jsonl(path: Path) -> list[PoseSample]:
    rows: list[PoseSample] = []
    with path.expanduser().open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {lineno}: {exc}") from exc
            position = obj.get("position")
            if not isinstance(position, dict):
                raise ValueError(f"missing position object at line {lineno}")
            rows.append(
                PoseSample(
                    t_s=_finite(obj.get("t_rel_s"), f"line {lineno} t_rel_s"),
                    x_m=_finite(position.get("x_m"), f"line {lineno} position.x_m"),
                    y_m=_finite(position.get("y_m"), f"line {lineno} position.y_m"),
                    z_m=_finite(position.get("z_m"), f"line {lineno} position.z_m"),
                )
            )
    return rows


def evaluate_collection(
    samples: list[PoseSample],
    *,
    record_duration_s: float = 90.0,
    analysis_start_s: float = 15.0,
    analysis_end_s: float = 75.0,
    min_analysis_rate_hz: float = 10.0,
    max_analysis_gap_s: float = 0.25,
    endpoint_tolerance_s: float = 1.0,
    analysis_coverage_tolerance_s: float = 0.25,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not samples:
        errors.append("vision_pose.jsonl contains no samples")
        return _summary(
            samples,
            [],
            errors,
            warnings,
            record_duration_s,
            analysis_start_s,
            analysis_end_s,
            min_analysis_rate_hz,
            max_analysis_gap_s,
        )

    times = [sample.t_s for sample in samples]
    non_monotonic = [
        index for index in range(1, len(times))
        if not times[index] > times[index - 1]
    ]
    if non_monotonic:
        errors.append(f"timestamps are not strictly increasing at {len(non_monotonic)} positions")

    first_t = times[0]
    last_t = times[-1]
    if first_t > endpoint_tolerance_s:
        errors.append(
            f"first sample at {first_t:.3f}s exceeds allowed startup coverage {endpoint_tolerance_s:.3f}s"
        )
    if last_t < record_duration_s - endpoint_tolerance_s:
        errors.append(
            f"last sample at {last_t:.3f}s does not cover the {record_duration_s:.1f}s record"
        )
    if last_t > record_duration_s + 5.0:
        warnings.append(
            f"last sample at {last_t:.3f}s exceeds requested duration by more than 5s"
        )

    analysis = [
        sample for sample in samples
        if analysis_start_s <= sample.t_s <= analysis_end_s
    ]
    if len(analysis) < 2:
        errors.append("fixed analysis window contains fewer than two samples")
    else:
        if analysis[0].t_s > analysis_start_s + analysis_coverage_tolerance_s:
            errors.append(
                f"analysis coverage starts at {analysis[0].t_s:.3f}s, later than allowed"
            )
        if analysis[-1].t_s < analysis_end_s - analysis_coverage_tolerance_s:
            errors.append(
                f"analysis coverage ends at {analysis[-1].t_s:.3f}s, earlier than allowed"
            )
        analysis_span = analysis[-1].t_s - analysis[0].t_s
        analysis_rate = (len(analysis) - 1) / analysis_span if analysis_span > 0.0 else 0.0
        if analysis_rate < min_analysis_rate_hz:
            errors.append(
                f"analysis rate {analysis_rate:.3f}Hz is below declared minimum "
                f"{min_analysis_rate_hz:.3f}Hz"
            )
        gaps = [
            analysis[index].t_s - analysis[index - 1].t_s
            for index in range(1, len(analysis))
        ]
        max_gap = max(gaps, default=0.0)
        if max_gap > max_analysis_gap_s:
            errors.append(
                f"maximum analysis-window sample gap {max_gap:.3f}s exceeds "
                f"{max_analysis_gap_s:.3f}s"
            )

    return _summary(
        samples,
        analysis,
        errors,
        warnings,
        record_duration_s,
        analysis_start_s,
        analysis_end_s,
        min_analysis_rate_hz,
        max_analysis_gap_s,
    )


def evaluate_path(path: Path, **kwargs: Any) -> dict[str, Any]:
    try:
        samples = load_vision_jsonl(path)
    except (OSError, ValueError) as exc:
        return {
            "status": REJECT,
            "acceptable": False,
            "accuracy_status": ACCURACY_BOUNDARY,
            "source": str(path.expanduser()),
            "errors": [str(exc)],
            "warnings": [],
        }
    result = evaluate_collection(samples, **kwargs)
    result["source"] = str(path.expanduser())
    return result


def write_report(summary: dict[str, Any], json_out: Path, md_out: Path) -> None:
    json_out = json_out.expanduser()
    md_out = md_out.expanduser()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Controlled R Collection Quality Gate",
        "",
        f"- Status: `{summary['status']}`",
        f"- Accuracy status: `{summary['accuracy_status']}`",
        f"- Source: `{summary.get('source', 'unknown')}`",
        f"- Total samples: `{summary.get('total_samples', 0)}`",
        f"- Fixed-window samples: `{summary.get('analysis_samples', 0)}`",
        f"- Fixed-window rate: `{_fmt(summary.get('analysis_rate_hz'))} Hz`",
        f"- Maximum fixed-window gap: `{_fmt(summary.get('max_analysis_gap_s'))} s`",
        "",
        "## Errors",
        "",
    ]
    errors = summary.get("errors", [])
    lines.extend([f"- {error}" for error in errors] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    warnings = summary.get("warnings", [])
    lines.extend([f"- {warning}" for warning in warnings] or ["- None"])
    lines.extend(
        [
            "",
            "> Passing this gate only confirms timing/sample coverage for the predeclared "
            "fixed-window noise analysis. It does not validate tracker accuracy.",
            "",
        ]
    )
    md_out.write_text("\n".join(lines), encoding="utf-8")


def _summary(
    samples: list[PoseSample],
    analysis: list[PoseSample],
    errors: list[str],
    warnings: list[str],
    record_duration_s: float,
    analysis_start_s: float,
    analysis_end_s: float,
    min_analysis_rate_hz: float,
    max_analysis_gap_limit_s: float,
) -> dict[str, Any]:
    analysis_span = (
        analysis[-1].t_s - analysis[0].t_s
        if len(analysis) >= 2
        else None
    )
    rate = (
        (len(analysis) - 1) / analysis_span
        if analysis_span is not None and analysis_span > 0.0
        else None
    )
    gaps = [
        analysis[index].t_s - analysis[index - 1].t_s
        for index in range(1, len(analysis))
    ]
    status = ACCEPTABLE if not errors else REJECT
    return {
        "status": status,
        "acceptable": not errors,
        "accuracy_status": ACCURACY_BOUNDARY,
        "declared_criteria": {
            "record_duration_s": record_duration_s,
            "analysis_window_s": [analysis_start_s, analysis_end_s],
            "min_analysis_rate_hz": min_analysis_rate_hz,
            "max_analysis_gap_s": max_analysis_gap_limit_s,
        },
        "total_samples": len(samples),
        "first_sample_s": samples[0].t_s if samples else None,
        "last_sample_s": samples[-1].t_s if samples else None,
        "analysis_samples": len(analysis),
        "analysis_first_sample_s": analysis[0].t_s if analysis else None,
        "analysis_last_sample_s": analysis[-1].t_s if analysis else None,
        "analysis_span_s": analysis_span,
        "analysis_rate_hz": rate,
        "max_analysis_gap_s": max(gaps) if gaps else None,
        "errors": errors,
        "warnings": warnings,
    }


def _finite(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric; got {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label} must be finite; got {value!r}")
    return out


def _fmt(value: Any) -> str:
    return "NA" if value is None else f"{float(value):.6g}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate GHOST controlled-R collection coverage.")
    parser.add_argument("vision_jsonl", type=Path)
    parser.add_argument("--record-duration-s", type=float, default=90.0)
    parser.add_argument("--analysis-start-s", type=float, default=15.0)
    parser.add_argument("--analysis-end-s", type=float, default=75.0)
    parser.add_argument("--min-analysis-rate-hz", type=float, default=10.0)
    parser.add_argument("--max-analysis-gap-s", type=float, default=0.25)
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--md-out", required=True, type=Path)
    args = parser.parse_args(argv)

    summary = evaluate_path(
        args.vision_jsonl,
        record_duration_s=args.record_duration_s,
        analysis_start_s=args.analysis_start_s,
        analysis_end_s=args.analysis_end_s,
        min_analysis_rate_hz=args.min_analysis_rate_hz,
        max_analysis_gap_s=args.max_analysis_gap_s,
    )
    write_report(summary, args.json_out, args.md_out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["acceptable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
