import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Plot GHOST tracker sweep results")
    parser.add_argument("--csv", default="analysis/tracker_sweep.csv")
    parser.add_argument("--out", default="analysis/tracker_sweep_summary.png")
    parser.add_argument("--top", type=int, default=15)
    return parser.parse_args()


def load_rows(path):
    rows = []
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        raise SystemExit(f"No rows found in {path}")
    return rows


def main():
    args = parse_args()
    rows = load_rows(args.csv)
    rows = sorted(rows, key=lambda r: float(r["rms_error_m"]))
    top = rows[: args.top]

    labels = [
        f"a={float(r['accel_std']):.1f}, R={float(r['meas_std']):.2f}, gate={float(r['gate_chi2']):.1f}"
        for r in top
    ]
    rms = np.array([float(r["rms_error_m"]) for r in top])
    max_err = np.array([float(r["max_error_m"]) for r in top])
    rejected = np.array([int(float(r["rejected"])) for r in top])

    y = np.arange(len(top))
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [2.3, 1]})
    fig.suptitle("GHOST Tracker Parameter Sweep", fontsize=15, fontweight="bold")

    ax = axes[0]
    ax.barh(y - 0.18, rms, height=0.36, label="RMS error [m]", color="#1f77b4")
    ax.barh(y + 0.18, max_err, height=0.36, label="Max error [m]", color="#d62728")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("position error [m]")
    ax.grid(True, axis="x", alpha=0.3)
    ax.legend()

    ax = axes[1]
    ax.barh(y, rejected, color="#ff7f0e")
    ax.set_yticks(y)
    ax.set_yticklabels([])
    ax.invert_yaxis()
    ax.set_xlabel("rejected updates")
    ax.grid(True, axis="x", alpha=0.3)

    best = top[0]
    summary = (
        f"Best: accel={float(best['accel_std']):.2f}, "
        f"meas={float(best['meas_std']):.2f}, "
        f"gate={float(best['gate_chi2']):.3f}\\n"
        f"RMS={float(best['rms_error_m']):.3f} m, "
        f"max={float(best['max_error_m']):.3f} m, "
        f"rejected={int(float(best['rejected']))}"
    )
    fig.text(0.01, 0.015, summary, fontsize=10, family="monospace")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.05, 1, 0.94])
    fig.savefig(out, dpi=160)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
