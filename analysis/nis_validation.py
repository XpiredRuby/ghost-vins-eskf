#!/usr/bin/env python3
"""
NIS (Normalized Innovation Squared) validation gate.

Usage:
    python3 nis_validation.py --log <path> --dof <int> --confidence <float> [--fail-on-violation]

Exit codes:
    0  gate passes
    1  gate fails (only when --fail-on-violation is set)
"""

import argparse
import csv
import sys

from scipy.stats import chi2


def main():
    parser = argparse.ArgumentParser(description="NIS chi-squared gate for GHOST filter logs")
    parser.add_argument("--log",              required=True,  help="CSV file: timestamp_s, nis_value")
    parser.add_argument("--dof",              required=True,  type=int,   help="Degrees of freedom (3 for GHOST)")
    parser.add_argument("--confidence",       required=True,  type=float, help="Confidence level (0.95 for GHOST)")
    parser.add_argument("--fail-on-violation", action="store_true",       help="Exit 1 when gate fails")
    args = parser.parse_args()

    # Read CSV — skip header row if present
    nis_values = []
    with open(args.log, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            try:
                nis_values.append(float(row[1]))
            except (ValueError, IndexError):
                # Skip non-numeric rows (header or malformed)
                continue

    total = len(nis_values)
    if total == 0:
        print(f"ERROR: no valid NIS samples found in {args.log}")
        sys.exit(1)

    # chi-squared upper bound at the given confidence level
    upper_bound = chi2.ppf(args.confidence, df=args.dof)

    # Fraction of samples that exceed the upper bound
    violations = sum(1 for v in nis_values if v > upper_bound)
    violation_rate = violations / total

    # Gate passes when violation rate is within the expected tail mass
    expected_tail = 1.0 - args.confidence
    passed = violation_rate <= expected_tail

    print(f"NIS gate — {args.log}")
    print(f"  Samples      : {total}")
    print(f"  chi2 bound   : {upper_bound:.4f}  (dof={args.dof}, confidence={args.confidence})")
    print(f"  Violations   : {violations}  ({violation_rate * 100:.1f}%)")
    print(f"  Allowed tail : {expected_tail * 100:.1f}%")
    print(f"  Gate         : {'PASS' if passed else 'FAIL'}")

    if not passed and args.fail_on_violation:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
