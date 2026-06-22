import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class SweepResult:
    accel_std: float
    meas_std: float
    gate_chi2: float
    rms_error_m: float
    max_error_m: float
    mean_error_m: float
    rejected: int
    accepted: int


def parse_args():
    parser = argparse.ArgumentParser(description="Offline CV tracker tuning sweep for GHOST")
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.025)
    parser.add_argument("--dropout-start", type=float, default=12.0)
    parser.add_argument("--dropout-duration", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "tracker_sweep.csv"))
    return parser.parse_args()


def truth_state(t, radius=1.25, speed=0.45):
    x = radius * math.cos(speed * t)
    y = 0.65 * radius * math.sin(speed * t)
    vx = -radius * speed * math.sin(speed * t)
    vy = 0.65 * radius * speed * math.cos(speed * t)
    return np.array([[x], [y], [vx], [vy]], dtype=float)


def in_dropout(t, dropout_start, dropout_duration):
    if dropout_duration <= 0.0:
        return False
    period = dropout_start + dropout_duration + 8.0
    phase = t % period
    return dropout_start <= phase < dropout_start + dropout_duration


def predict(x, p, dt, accel_std):
    f = np.array(
        [
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    q = accel_std * accel_std
    q_mat = q * np.array(
        [
            [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
            [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
            [dt**3 / 2.0, 0.0, dt**2, 0.0],
            [0.0, dt**3 / 2.0, 0.0, dt**2],
        ]
    )
    return f @ x, f @ p @ f.T + q_mat


def run_trial(args, accel_std, meas_std, gate_chi2):
    rng = np.random.default_rng(args.seed)
    dt = 1.0 / args.rate
    ts = np.arange(0.0, args.duration, dt)
    h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    r = np.diag([meas_std * meas_std, meas_std * meas_std])
    x = np.zeros((4, 1))
    p = np.eye(4) * 1e3
    initialized = False
    errors = []
    accepted = 0
    rejected = 0

    for t in ts:
        truth = truth_state(float(t))

        if initialized:
            x, p = predict(x, p, dt, accel_std)

        if not in_dropout(float(t), args.dropout_start, args.dropout_duration):
            measurement = h @ truth + rng.normal(0.0, args.noise_std, size=(2, 1))

            if not initialized:
                x[:] = 0.0
                x[0, 0] = measurement[0, 0]
                x[1, 0] = measurement[1, 0]
                p = np.diag([0.05, 0.05, 1.0, 1.0])
                initialized = True
                accepted += 1
            else:
                innovation = measurement - h @ x
                s = h @ p @ h.T + r
                nis = float((innovation.T @ np.linalg.inv(s) @ innovation)[0, 0])
                if nis <= gate_chi2:
                    k = p @ h.T @ np.linalg.inv(s)
                    eye = np.eye(4)
                    x = x + k @ innovation
                    p = (eye - k @ h) @ p @ (eye - k @ h).T + k @ r @ k.T
                    accepted += 1
                else:
                    rejected += 1

        if initialized:
            err = float(np.linalg.norm(x[:2] - truth[:2]))
            errors.append(err)

    errors_arr = np.array(errors)
    return SweepResult(
        accel_std=accel_std,
        meas_std=meas_std,
        gate_chi2=gate_chi2,
        rms_error_m=float(np.sqrt(np.mean(errors_arr**2))),
        max_error_m=float(np.max(errors_arr)),
        mean_error_m=float(np.mean(errors_arr)),
        rejected=rejected,
        accepted=accepted,
    )


def main():
    args = parse_args()
    accel_values = [0.8, 1.0, 1.4, 2.0, 2.8]
    meas_values = [0.03, 0.05, 0.08, 0.12]
    gate_values = [5.991, 9.210, 11.829]

    results = []
    for accel_std in accel_values:
        for meas_std in meas_values:
            for gate_chi2 in gate_values:
                results.append(run_trial(args, accel_std, meas_std, gate_chi2))

    results.sort(key=lambda r: (r.rms_error_m, r.max_error_m))
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "accel_std",
                "meas_std",
                "gate_chi2",
                "rms_error_m",
                "max_error_m",
                "mean_error_m",
                "accepted",
                "rejected",
            ]
        )
        for i, result in enumerate(results, start=1):
            writer.writerow(
                [
                    i,
                    result.accel_std,
                    result.meas_std,
                    result.gate_chi2,
                    result.rms_error_m,
                    result.max_error_m,
                    result.mean_error_m,
                    result.accepted,
                    result.rejected,
                ]
            )

    print(f"saved: {out}")
    print("top 5:")
    for i, result in enumerate(results[:5], start=1):
        print(
            f"{i}: accel={result.accel_std:.2f} meas={result.meas_std:.2f} "
            f"gate={result.gate_chi2:.3f} rms={result.rms_error_m:.3f}m "
            f"max={result.max_error_m:.3f}m rejected={result.rejected}"
        )


if __name__ == "__main__":
    main()
