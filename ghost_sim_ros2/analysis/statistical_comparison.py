"""Paired statistical comparison helpers for IMM and MH validation trials."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from random import Random
from statistics import median
from typing import Iterable


def paired_comparison(
    imm_errors: Iterable[float],
    mh_errors: Iterable[float],
    condition_name: str,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, object]:
    imm = [_finite_float(value, "imm_errors") for value in imm_errors]
    mh = [_finite_float(value, "mh_errors") for value in mh_errors]
    if len(imm) != len(mh):
        raise ValueError(f"paired inputs must have equal length: IMM={len(imm)} MH={len(mh)}")
    if not imm:
        raise ValueError("paired inputs must contain at least one trial")
    if n_boot < 1:
        raise ValueError("n_boot must be >= 1")

    diffs = [mh_value - imm_value for imm_value, mh_value in zip(imm, mh)]
    boot = _bootstrap_median_ci(diffs, n_boot=n_boot, seed=seed)
    wilcoxon = _wilcoxon(diffs)

    return {
        "condition": condition_name,
        "n_trials": len(imm),
        "median_imm_error": median(imm),
        "median_mh_error": median(mh),
        "median_error_difference_mh_minus_imm": median(diffs),
        "median_error_reduction_mh_vs_imm": median(imm) - median(mh),
        "bootstrap_ci_95_mh_minus_imm": {
            "low": boot[0],
            "high": boot[1],
            "n_boot": n_boot,
            "seed": seed,
        },
        **wilcoxon,
    }


def _bootstrap_median_ci(diffs: list[float], n_boot: int, seed: int) -> tuple[float, float]:
    rng = Random(seed)
    n = len(diffs)
    medians = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        medians.append(median(sample))
    medians.sort()
    return (_quantile_sorted(medians, 0.025), _quantile_sorted(medians, 0.975))


def _wilcoxon(diffs: list[float]) -> dict[str, object]:
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        return {
            "wilcoxon_available": False,
            "wilcoxon_statistic": None,
            "wilcoxon_p_value": None,
        }

    if all(diff == 0.0 for diff in diffs):
        return {
            "wilcoxon_available": True,
            "wilcoxon_statistic": 0.0,
            "wilcoxon_p_value": 1.0,
        }
    result = wilcoxon(diffs)
    return {
        "wilcoxon_available": True,
        "wilcoxon_statistic": float(result.statistic),
        "wilcoxon_p_value": float(result.pvalue),
    }


def _quantile_sorted(values: list[float], q: float) -> float:
    if len(values) == 1:
        return values[0]
    position = q * (len(values) - 1)
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return values[lo]
    fraction = position - lo
    return values[lo] * (1.0 - fraction) + values[hi] * fraction


def _finite_float(value: float, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} values must be finite; got {value!r}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paired IMM/MH statistical comparison.")
    parser.add_argument("--imm-errors", required=True, help="Comma-separated IMM error values")
    parser.add_argument("--mh-errors", required=True, help="Comma-separated MH error values")
    parser.add_argument("--condition", required=True)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    result = paired_comparison(
        _parse_errors(args.imm_errors),
        _parse_errors(args.mh_errors),
        args.condition,
        n_boot=args.n_boot,
        seed=args.seed,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().parent.mkdir(parents=True, exist_ok=True)
        args.out.expanduser().write_text(text, encoding="utf-8")
        print(f"wrote: {args.out.expanduser()}")
    else:
        print(text, end="")
    return 0


def _parse_errors(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
