"""Generate recruiter- and engineer-facing plots from grid validation summary JSON."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate_grid_visuals(summary_path: Path, out_dir: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or not isinstance(summary.get("points"), list):
        raise ValueError("grid summary must contain a points list")
    points = [point for point in summary["points"] if _finite(point.get("error_m"))]
    if not points:
        raise ValueError("grid summary contains no finite point errors")
    out_dir = out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    _true_vs_measured(points, out_dir / "grid_true_vs_measured.png")
    _error_vectors(points, out_dir / "grid_error_vectors.png")
    _point_errors(points, out_dir / "grid_point_errors.png")
    _spatial_error_map(points, out_dir / "grid_spatial_error_map.png")
    report = {
        "source_summary": str(summary_path.expanduser()),
        "n_points": len(points),
        "aggregate": summary.get("aggregate", {}),
        "plots": [
            "grid_true_vs_measured.png",
            "grid_error_vectors.png",
            "grid_point_errors.png",
            "grid_spatial_error_map.png",
        ],
        "visualization_boundary": "DISCRETE_MEASURED_POINTS_ONLY_NO_INTERPOLATED_ACCURACY_SURFACE_CLAIM",
    }
    (out_dir / "grid_visuals_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "grid_validation_dashboard.html").write_text(
        _html_report(summary, report), encoding="utf-8"
    )
    return report


def _true_vs_measured(points, path):
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(
        [p["x_true_m"] for p in points],
        [p["y_true_m"] for p in points],
        marker="x",
        s=80,
        label="Physical truth",
    )
    ax.scatter(
        [p["x_mean_m"] for p in points],
        [p["y_mean_m"] for p in points],
        marker="o",
        s=55,
        label="Measured mean",
    )
    for p in points:
        ax.plot(
            [p["x_true_m"], p["x_mean_m"]],
            [p["y_true_m"], p["y_mean_m"]],
            linewidth=1,
        )
        ax.annotate(
            str(p["point_id"]),
            (p["x_true_m"], p["y_true_m"]),
            xytext=(5, 5),
            textcoords="offset points",
        )
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Measured AprilTag position versus physical grid truth")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _error_vectors(points, path):
    fig, ax = plt.subplots(figsize=(7, 6))
    x = [p["x_true_m"] for p in points]
    y = [p["y_true_m"] for p in points]
    dx = [p["dx_m"] for p in points]
    dy = [p["dy_m"] for p in points]
    ax.quiver(x, y, dx, dy, angles="xy", scale_units="xy", scale=1)
    ax.scatter(x, y, marker="o")
    for p in points:
        ax.annotate(
            f"{p['point_id']}\n{p['error_m']:.4g} m",
            (p["x_true_m"], p["y_true_m"]),
            xytext=(6, 6),
            textcoords="offset points",
        )
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("truth x (m)")
    ax.set_ylabel("truth y (m)")
    ax.set_title("Grid error vectors (true point to measured mean)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _point_errors(points, path):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [str(p["point_id"]) for p in points]
    values = [p["error_m"] for p in points]
    ax.bar(labels, values)
    ax.set_xlabel("Grid point")
    ax.set_ylabel("Euclidean error (m)")
    ax.set_title("Per-point AprilTag position error")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _spatial_error_map(points, path):
    fig, ax = plt.subplots(figsize=(7, 6))
    scatter = ax.scatter(
        [p["x_true_m"] for p in points],
        [p["y_true_m"] for p in points],
        c=[p["error_m"] for p in points],
        s=[max(70, 1200 * p["error_m"]) for p in points],
    )
    for p in points:
        ax.annotate(
            str(p["point_id"]),
            (p["x_true_m"], p["y_true_m"]),
            ha="center",
            va="center",
        )
    fig.colorbar(scatter, ax=ax, label="Euclidean error (m)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("truth x (m)")
    ax.set_ylabel("truth y (m)")
    ax.set_title("Discrete spatial error map (no interpolation)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _html_report(summary, report):
    agg = summary.get("aggregate", {})
    cards = "".join(
        f"<div class='card'><strong>{label}</strong><span>{value}</span></div>"
        for label, value in [
            ("Grid points", report["n_points"]),
            ("RMSE", _format_m(agg.get("rmse_m"))),
            ("Mean error", _format_m(agg.get("mean_error_m"))),
            ("Maximum error", _format_m(agg.get("max_error_m"))),
            ("Bias x", _format_m(agg.get("bias_x_m"))),
            ("Bias y", _format_m(agg.get("bias_y_m"))),
        ]
    )
    figures = "".join(
        f"<article><img src='{name}' alt='{name}'><h2>{title}</h2></article>"
        for title, name in [
            ("Truth versus measured means", "grid_true_vs_measured.png"),
            ("Error vectors", "grid_error_vectors.png"),
            ("Per-point errors", "grid_point_errors.png"),
            ("Discrete spatial error map", "grid_spatial_error_map.png"),
        ]
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>GHOST Grid Validation</title><style>body{{margin:0;background:#07111f;color:#f4f8ff;font-family:system-ui,sans-serif}}main{{width:min(1150px,calc(100% - 30px));margin:auto;padding:34px 0}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card,article{{border:1px solid #29405f;background:#102036;border-radius:14px;padding:16px}}.card strong,.card span{{display:block}}.card span,p{{color:#a9bbd3}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:22px}}img{{width:100%;background:white;border-radius:8px}}.note{{border-left:4px solid #ffb454;background:#201506;padding:14px}}@media(max-width:800px){{.cards,.grid{{grid-template-columns:1fr}}}}</style></head><body><main><h1>GHOST Ground-Truth Grid Validation</h1><p>Measured AprilTag means compared with discrete physical grid coordinates.</p><div class='note'>{report['visualization_boundary']}</div><div class='cards'>{cards}</div><div class='grid'>{figures}</div></main></body></html>"""


def _format_m(value):
    return "NA" if not _finite(value) else f"{float(value):.6g} m"


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate GHOST ground-truth grid validation plots and dashboard."
    )
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    report = generate_grid_visuals(args.summary, args.out_dir)
    print(f"plots={len(report['plots'])}")
    print(f"wrote={args.out_dir.expanduser() / 'grid_validation_dashboard.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
