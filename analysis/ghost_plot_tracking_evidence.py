import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Plot GHOST tracking evidence CSV")
    parser.add_argument("--csv", default=str(Path.home() / "ghost_logs" / "sim_tracking.csv"))
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_tracking_evidence.png"))
    return parser.parse_args()


def to_float(value):
    if value is None or value == "":
        return math.nan
    return float(value)


def load_rows(path):
    rows = []
    with Path(path).expanduser().open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({key: to_float(value) for key, value in row.items()})
    if not rows:
        raise SystemExit(f"No rows found in {path}")
    return rows


def column(rows, name):
    return np.array([row[name] for row in rows], dtype=float)


def main():
    args = parse_args()
    rows = load_rows(args.csv)

    t = column(rows, "time_s")
    t = t - t[0]

    meas_x = column(rows, "meas_x_m")
    meas_y = column(rows, "meas_y_m")
    truth_x = column(rows, "truth_x_m")
    truth_y = column(rows, "truth_y_m")
    est_x = column(rows, "est_x_m")
    est_y = column(rows, "est_y_m")
    p_xx = column(rows, "p_xx")
    p_yy = column(rows, "p_yy")

    truth_valid = np.isfinite(truth_x) & np.isfinite(truth_y)
    meas_valid = np.isfinite(meas_x) & np.isfinite(meas_y)
    est_valid = np.isfinite(est_x) & np.isfinite(est_y)
    err = np.sqrt((est_x - truth_x) ** 2 + (est_y - truth_y) ** 2)
    sigma_pos = np.sqrt(np.maximum(p_xx, 0.0) + np.maximum(p_yy, 0.0))

    rms = float(np.sqrt(np.nanmean(err[truth_valid & est_valid] ** 2)))
    max_err = float(np.nanmax(err[truth_valid & est_valid]))
    duration = float(t[-1])
    samples = len(rows)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(
        f"GHOST ROS2 Synthetic Tracking Evidence | samples={samples} | duration={duration:.1f}s | RMS error={rms:.3f}m",
        fontsize=13,
        fontweight="bold",
    )

    ax = axes[0, 0]
    ax.plot(truth_x[truth_valid], truth_y[truth_valid], "k-", linewidth=2, label="truth")
    ax.scatter(meas_x[meas_valid], meas_y[meas_valid], s=6, alpha=0.25, label="measurements")
    ax.plot(est_x[est_valid], est_y[est_valid], color="#1f77b4", linewidth=2, label="tracker estimate")
    ax.set_title("2D Trajectory")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[0, 1]
    ax.plot(t, err, color="#d62728", linewidth=1.5)
    ax.set_title(f"Position Error | max={max_err:.3f}m")
    ax.set_xlabel("time [s]")
    ax.set_ylabel("error [m]")
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    ax.plot(t, p_xx, label="Pxx")
    ax.plot(t, p_yy, label="Pyy")
    ax.set_title("Position Covariance")
    ax.set_xlabel("time [s]")
    ax.set_ylabel("variance [m^2]")
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[1, 1]
    ax.plot(t, sigma_pos, color="#9467bd", linewidth=1.5)
    ax.set_title("Combined Position Sigma Proxy")
    ax.set_xlabel("time [s]")
    ax.set_ylabel("sqrt(Pxx + Pyy) [m]")
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)

    print(f"rows: {samples}")
    print(f"duration_s: {duration:.2f}")
    print(f"rms_error_m: {rms:.4f}")
    print(f"max_error_m: {max_err:.4f}")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
