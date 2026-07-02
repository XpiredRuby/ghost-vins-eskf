import atexit
import json
import math
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Any

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.fp = path.open("a", encoding="utf-8", buffering=1)

    def write(self, row: dict[str, Any]) -> None:
        self.fp.write(json.dumps(row, separators=(",", ":")) + "\n")
        self.fp.flush()

    def close(self) -> None:
        try:
            self.fp.flush()
            self.fp.close()
        except Exception:
            pass


class GhostTrialRecorder(Node):
    """Records a live GHOST-MH run into replayable JSONL logs.

    Output folder:
        ~/ghost_logs/trials/<trial_id>/

    Files:
        metadata.json
        futures.jsonl
        status.jsonl
        vision_pose.jsonl
        events.jsonl
        metrics.jsonl
        summary.json
        summary.md
    """

    def __init__(self) -> None:
        super().__init__("ghost_trial_recorder")

        self.declare_parameter("trial_root", str(Path.home() / "ghost_logs" / "trials"))
        self.declare_parameter("futures_topic", "/ghost/tracker_mh/futures_json")
        self.declare_parameter("status_topic", "/ghost/tracker_mh/status")
        self.declare_parameter("vision_topic", "/ghost/vision/target_pose")
        self.declare_parameter("events_topic", "/ghost/trial/events_json")
        self.declare_parameter("summary_topic", "/ghost/trial/summary_json")
        self.declare_parameter("report_period_s", 1.0)

        self.start_wall_s = time_now_s()
        self.start_ros_s = self.now_s()
        self.trial_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.trial_dir = Path(str(self.get_parameter("trial_root").value)).expanduser() / self.trial_id
        self.trial_dir.mkdir(parents=True, exist_ok=True)

        self.futures_log = JsonlWriter(self.trial_dir / "futures.jsonl")
        self.status_log = JsonlWriter(self.trial_dir / "status.jsonl")
        self.vision_log = JsonlWriter(self.trial_dir / "vision_pose.jsonl")
        self.events_log = JsonlWriter(self.trial_dir / "events.jsonl")
        self.metrics_log = JsonlWriter(self.trial_dir / "metrics.jsonl")

        self.events: list[dict[str, Any]] = []
        self.metrics: list[dict[str, Any]] = []
        self.latest_payload: dict[str, Any] | None = None
        self.last_hidden_payload: dict[str, Any] | None = None
        self.last_visible_estimate: dict[str, Any] | None = None
        self.occlusion_start_estimate: dict[str, Any] | None = None
        self.occlusion_start_ros_s: float | None = None
        self.occlusion_count = 0
        self.reacquire_count = 0
        self.reset_count = 0
        self.previous_visible = False
        self.previous_initialized = False
        self.finalized = False

        qos = QoSProfile(depth=10)
        self.create_subscription(
            String,
            str(self.get_parameter("futures_topic").value),
            self.on_futures,
            qos,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("status_topic").value),
            self.on_status,
            qos,
        )
        self.create_subscription(
            PoseWithCovarianceStamped,
            str(self.get_parameter("vision_topic").value),
            self.on_vision,
            qos,
        )
        self.events_pub = self.create_publisher(String, str(self.get_parameter("events_topic").value), qos)
        self.summary_pub = self.create_publisher(String, str(self.get_parameter("summary_topic").value), qos)

        self.write_metadata()
        self.emit_event("TRIAL_START", "Trial recording started", {})
        self.create_timer(float(self.get_parameter("report_period_s").value), self.write_summary_safe)

        atexit.register(self.finalize)
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        except Exception:
            pass

        self.get_logger().info(f"GHOST trial recorder writing to {self.trial_dir}")

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def t_rel(self) -> float:
        return max(0.0, self.now_s() - self.start_ros_s)

    def base_row(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "wall_time_s": time_now_s(),
            "ros_time_s": self.now_s(),
            "t_rel_s": self.t_rel(),
        }

    def write_metadata(self) -> None:
        metadata = {
            "trial_id": self.trial_id,
            "created_local": datetime.now().isoformat(timespec="seconds"),
            "trial_dir": str(self.trial_dir),
            "topics": {
                "futures": str(self.get_parameter("futures_topic").value),
                "status": str(self.get_parameter("status_topic").value),
                "vision": str(self.get_parameter("vision_topic").value),
                "events": str(self.get_parameter("events_topic").value),
                "summary": str(self.get_parameter("summary_topic").value),
            },
            "purpose": "Live GHOST-MH trial recording for replay, baseline comparison, and report export.",
        }
        (self.trial_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def on_status(self, msg: String) -> None:
        row = self.base_row()
        row["status"] = msg.data
        self.status_log.write(row)

    def on_vision(self, msg: PoseWithCovarianceStamped) -> None:
        row = self.base_row()
        row["position"] = {
            "x_m": float(msg.pose.pose.position.x),
            "y_m": float(msg.pose.pose.position.y),
            "z_m": float(msg.pose.pose.position.z),
        }
        row["stamp"] = {
            "sec": int(msg.header.stamp.sec),
            "nanosec": int(msg.header.stamp.nanosec),
        }
        self.vision_log.write(row)

    def on_futures(self, msg: String) -> None:
        row = self.base_row()
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            row["error"] = "bad_json"
            row["raw"] = msg.data[:500]
            self.futures_log.write(row)
            return

        row["payload"] = payload
        self.futures_log.write(row)
        self.latest_payload = payload
        self.update_state_machine(payload)

    def update_state_machine(self, payload: dict[str, Any]) -> None:
        initialized = bool(payload.get("initialized"))
        visible = bool(payload.get("visible"))
        estimate = payload.get("estimate")

        if initialized and not self.previous_initialized:
            self.emit_event("TRACKER_INITIALIZED", "Tracker initialized", {"estimate": estimate})

        if visible and estimate:
            if not self.previous_visible:
                if self.occlusion_start_ros_s is not None:
                    self.reacquire_count += 1
                    metric = self.compute_reacquisition_metric(payload)
                    self.metrics.append(metric)
                    self.metrics_log.write(metric)
                    self.emit_event("REACQUIRED", "Target reacquired after occlusion", metric)
                    self.occlusion_start_ros_s = None
                    self.occlusion_start_estimate = None
                else:
                    self.emit_event("TARGET_LOCK", "Visible target lock", {"estimate": estimate})
            self.last_visible_estimate = estimate

        if initialized and not visible:
            self.last_hidden_payload = payload
            if self.previous_visible:
                self.occlusion_count += 1
                self.occlusion_start_ros_s = self.now_s()
                self.occlusion_start_estimate = self.last_visible_estimate
                self.emit_event(
                    "OCCLUSION_START",
                    "Measurement lost; GHOST-MH predicting bounded futures",
                    {"last_visible_estimate": self.last_visible_estimate},
                )

        if not initialized and self.previous_initialized:
            self.reset_count += 1
            self.emit_event("RESET", "Tracker reset / no valid target state", {})
            self.occlusion_start_ros_s = None
            self.occlusion_start_estimate = None

        self.previous_visible = visible
        self.previous_initialized = initialized

    def compute_reacquisition_metric(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.base_row()
        row["event"] = "REACQUISITION_METRIC"
        estimate = payload.get("estimate") or {}
        x = as_float(estimate.get("x_m"))
        y = as_float(estimate.get("y_m"))
        row["truth_proxy"] = {"x_m": x, "y_m": y, "source": "reacquired_estimate"}

        dt = None
        if self.occlusion_start_ros_s is not None:
            dt = max(0.0, self.now_s() - self.occlusion_start_ros_s)
        row["occlusion_duration_s"] = dt

        start = self.occlusion_start_estimate or self.last_visible_estimate or {}
        sx = as_float(start.get("x_m"))
        sy = as_float(start.get("y_m"))
        svx = as_float(start.get("vx_mps"))
        svy = as_float(start.get("vy_mps"))

        hold_pred = {"x_m": sx, "y_m": sy}
        cv_pred = {"x_m": None, "y_m": None}
        if dt is not None and sx is not None and sy is not None and svx is not None and svy is not None:
            cv_pred = {"x_m": sx + svx * dt, "y_m": sy + svy * dt}

        row["baselines"] = {
            "last_seen_hold": {
                "prediction": hold_pred,
                "error_m": dist_xy(x, y, hold_pred.get("x_m"), hold_pred.get("y_m")),
            },
            "constant_velocity": {
                "prediction": cv_pred,
                "error_m": dist_xy(x, y, cv_pred.get("x_m"), cv_pred.get("y_m")),
            },
        }

        hypotheses = []
        if self.last_hidden_payload:
            hypotheses = list(self.last_hidden_payload.get("hypotheses") or [])

        ghost_rows = []
        for hyp in hypotheses[:5]:
            hx = as_float(hyp.get("x_m"))
            hy = as_float(hyp.get("y_m"))
            ghost_rows.append(
                {
                    "rank": hyp.get("rank"),
                    "model": hyp.get("model"),
                    "probability": hyp.get("probability"),
                    "prediction": {"x_m": hx, "y_m": hy},
                    "error_m": dist_xy(x, y, hx, hy),
                }
            )
        row["ghost_mh"] = {
            "top_hypotheses": ghost_rows,
            "top1_error_m": ghost_rows[0]["error_m"] if ghost_rows else None,
            "top3_best_error_m": min_ignore_none([g["error_m"] for g in ghost_rows[:3]]),
            "top5_best_error_m": min_ignore_none([g["error_m"] for g in ghost_rows[:5]]),
        }

        cv_err = row["baselines"]["constant_velocity"]["error_m"]
        top1_err = row["ghost_mh"]["top1_error_m"]
        top3_err = row["ghost_mh"]["top3_best_error_m"]
        row["comparisons"] = {
            "top1_beats_cv": bool(top1_err is not None and cv_err is not None and top1_err < cv_err),
            "top3_beats_cv": bool(top3_err is not None and cv_err is not None and top3_err < cv_err),
        }
        return row

    def emit_event(self, event_type: str, message: str, details: dict[str, Any]) -> None:
        row = self.base_row()
        row.update({"event": event_type, "message": message, "details": details})
        self.events.append(row)
        self.events_log.write(row)
        self.events_pub.publish(String(data=json.dumps(row, separators=(",", ":"))))

    def summary(self) -> dict[str, Any]:
        duration_s = max(0.0, time_now_s() - self.start_wall_s)
        cv_errors = [m.get("baselines", {}).get("constant_velocity", {}).get("error_m") for m in self.metrics]
        hold_errors = [m.get("baselines", {}).get("last_seen_hold", {}).get("error_m") for m in self.metrics]
        top1_errors = [m.get("ghost_mh", {}).get("top1_error_m") for m in self.metrics]
        top3_errors = [m.get("ghost_mh", {}).get("top3_best_error_m") for m in self.metrics]

        result = {
            "trial_id": self.trial_id,
            "trial_dir": str(self.trial_dir),
            "duration_s": duration_s,
            "event_count": len(self.events),
            "occlusion_count": self.occlusion_count,
            "reacquire_count": self.reacquire_count,
            "reset_count": self.reset_count,
            "metric_count": len(self.metrics),
            "errors_m": {
                "last_seen_hold_mean": mean_ignore_none(hold_errors),
                "constant_velocity_mean": mean_ignore_none(cv_errors),
                "ghost_top1_mean": mean_ignore_none(top1_errors),
                "ghost_top3_best_mean": mean_ignore_none(top3_errors),
                "constant_velocity_95p": percentile_ignore_none(cv_errors, 95.0),
                "ghost_top1_95p": percentile_ignore_none(top1_errors, 95.0),
                "ghost_top3_best_95p": percentile_ignore_none(top3_errors, 95.0),
            },
            "coverage": {
                "top1_beats_cv_count": sum(1 for m in self.metrics if m.get("comparisons", {}).get("top1_beats_cv")),
                "top3_beats_cv_count": sum(1 for m in self.metrics if m.get("comparisons", {}).get("top3_beats_cv")),
            },
            "latest_event": self.events[-1] if self.events else None,
        }
        return result

    def write_summary_safe(self) -> None:
        try:
            summary = self.summary()
            (self.trial_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            (self.trial_dir / "summary.md").write_text(self.summary_markdown(summary), encoding="utf-8")
            self.summary_pub.publish(String(data=json.dumps(summary, separators=(",", ":"))))
        except Exception as exc:
            self.get_logger().warn(f"Failed writing trial summary: {exc}")

    def summary_markdown(self, summary: dict[str, Any]) -> str:
        errors = summary.get("errors_m", {})
        coverage = summary.get("coverage", {})
        lines = [
            f"# GHOST-MH Trial Report — {summary.get('trial_id')}",
            "",
            f"Trial directory: `{summary.get('trial_dir')}`",
            f"Duration: `{summary.get('duration_s', 0.0):.2f} s`",
            "",
            "## Event Summary",
            "",
            f"- Events: `{summary.get('event_count')}`",
            f"- Occlusions: `{summary.get('occlusion_count')}`",
            f"- Reacquisitions: `{summary.get('reacquire_count')}`",
            f"- Resets: `{summary.get('reset_count')}`",
            "",
            "## Error Metrics at Reacquisition",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Last-seen hold mean error | {fmt_m(errors.get('last_seen_hold_mean'))} |",
            f"| Constant-velocity mean error | {fmt_m(errors.get('constant_velocity_mean'))} |",
            f"| GHOST top-1 mean error | {fmt_m(errors.get('ghost_top1_mean'))} |",
            f"| GHOST top-3 best mean error | {fmt_m(errors.get('ghost_top3_best_mean'))} |",
            f"| Constant-velocity 95th percentile | {fmt_m(errors.get('constant_velocity_95p'))} |",
            f"| GHOST top-1 95th percentile | {fmt_m(errors.get('ghost_top1_95p'))} |",
            f"| GHOST top-3 best 95th percentile | {fmt_m(errors.get('ghost_top3_best_95p'))} |",
            "",
            "## Baseline Comparison Counts",
            "",
            f"- Top-1 beats CV: `{coverage.get('top1_beats_cv_count')}`",
            f"- Top-3 beats CV: `{coverage.get('top3_beats_cv_count')}`",
            "",
            "## Notes",
            "",
            "The reacquired estimate is used as the practical truth proxy for this live prototype. A measured floor grid should be used for final ground-truth validation.",
            "",
        ]
        return "\n".join(lines)

    def finalize(self) -> None:
        if self.finalized:
            return
        self.finalized = True
        try:
            self.emit_event("TRIAL_END", "Trial recording stopped", {})
            self.write_summary_safe()
        except Exception:
            pass
        for writer in [self.futures_log, self.status_log, self.vision_log, self.events_log, self.metrics_log]:
            writer.close()

    def _handle_signal(self, signum: int, frame: Any) -> None:
        self.finalize()
        try:
            rclpy.shutdown()
        except Exception:
            pass
        raise SystemExit(0)

    def destroy_node(self) -> bool:
        self.finalize()
        return super().destroy_node()


def as_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def dist_xy(x1: float | None, y1: float | None, x2: float | None, y2: float | None) -> float | None:
    if x1 is None or y1 is None or x2 is None or y2 is None:
        return None
    return math.hypot(x1 - x2, y1 - y2)


def min_ignore_none(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    return min(clean) if clean else None


def mean_ignore_none(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    return sum(clean) / len(clean) if clean else None


def percentile_ignore_none(values: list[float | None], p: float) -> float | None:
    clean = sorted(v for v in values if v is not None and math.isfinite(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    k = (len(clean) - 1) * p / 100.0
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return clean[lo]
    return clean[lo] * (hi - k) + clean[hi] * (k - lo)


def fmt_m(value: Any) -> str:
    f = as_float(value)
    if f is None:
        return "n/a"
    return f"{f:.4f} m"


def time_now_s() -> float:
    import time

    return time.time()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = GhostTrialRecorder()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
