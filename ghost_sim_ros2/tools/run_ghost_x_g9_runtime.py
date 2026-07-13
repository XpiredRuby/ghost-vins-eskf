#!/usr/bin/env python3
"""Execute GHOST-X G9 ROS 2 QoS, timing, resource, and estimator benchmarks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.event_handler import PublisherEventCallbacks, SubscriptionEventCallbacks
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    LivelinessPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from rclpy.utilities import get_rmw_implementation_identifier
from std_msgs.msg import String

from analysis.ghost_x_runtime import (
    ResourceSampler,
    benchmark_cpp_estimators,
    benchmark_python_estimators,
    cpu_stress,
    evaluate_estimator_deadline,
    load_runtime_design,
    max_rss_mb,
    read_throttled_status,
    summarize_resources,
    summarize_samples,
)


def _event_payload(event: Any) -> dict[str, Any]:
    fields = {}
    for name in (
        "total_count",
        "total_count_change",
        "alive_count",
        "not_alive_count",
        "alive_count_change",
        "not_alive_count_change",
        "current_count",
        "current_count_change",
        "last_policy_kind",
    ):
        if hasattr(event, name):
            value = getattr(event, name)
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = str(value)
            fields[name] = value
    return fields


def _reliability(value: str) -> ReliabilityPolicy:
    normalized = str(value).lower()
    if normalized == "best_effort":
        return ReliabilityPolicy.BEST_EFFORT
    if normalized == "reliable":
        return ReliabilityPolicy.RELIABLE
    raise ValueError(f"unknown reliability: {value}")


def _liveliness(value: str | None) -> LivelinessPolicy:
    normalized = str(value or "automatic").lower()
    if normalized == "automatic":
        return LivelinessPolicy.AUTOMATIC
    if normalized == "manual_by_topic":
        return LivelinessPolicy.MANUAL_BY_TOPIC
    raise ValueError(f"unknown liveliness: {value}")


def build_qos(scenario: dict[str, Any], role: str) -> QoSProfile:
    reliability_key = "publisher_reliability" if role == "publisher" else "subscriber_reliability"
    history = HistoryPolicy.KEEP_LAST if str(scenario.get("history", "keep_last")) == "keep_last" else HistoryPolicy.KEEP_ALL
    kwargs: dict[str, Any] = {
        "history": history,
        "depth": int(scenario.get("depth", 10)),
        "reliability": _reliability(str(scenario[reliability_key])),
        "durability": DurabilityPolicy.VOLATILE,
        "liveliness": _liveliness(scenario.get("liveliness")),
    }
    if scenario.get("deadline_ms") is not None:
        kwargs["deadline"] = Duration(nanoseconds=int(float(scenario["deadline_ms"]) * 1.0e6))
    if scenario.get("liveliness_lease_ms") is not None:
        kwargs["liveliness_lease_duration"] = Duration(
            nanoseconds=int(float(scenario["liveliness_lease_ms"]) * 1.0e6)
        )
    return QoSProfile(**kwargs)


class BenchmarkPublisher(Node):
    def __init__(self, scenario: dict[str, Any], topic: str, payload_bytes: int) -> None:
        super().__init__(f"ghost_g9_pub_{scenario['id']}")
        self.scenario = scenario
        self.payload = "x" * max(0, int(payload_bytes))
        self.sequence = 0
        self.published = 0
        self.active = False
        self.collect_events = False
        self.start_time = 0.0
        self.events: dict[str, list[dict[str, Any]]] = {
            "deadline": [],
            "liveliness": [],
            "incompatible_qos": [],
            "matched": [],
        }
        callbacks = PublisherEventCallbacks(
            deadline=lambda event: self._event("deadline", event),
            liveliness=lambda event: self._event("liveliness", event),
            incompatible_qos=lambda event: self._event("incompatible_qos", event),
            matched=lambda event: self._event("matched", event),
            use_default_callbacks=False,
        )
        self.publisher = self.create_publisher(
            String,
            topic,
            build_qos(scenario, "publisher"),
            event_callbacks=callbacks,
            callback_group=ReentrantCallbackGroup(),
        )
        self.timer = self.create_timer(
            1.0 / float(scenario["rate_hz"]),
            self._on_timer,
            callback_group=ReentrantCallbackGroup(),
        )

    def begin(self) -> None:
        self.sequence = 0
        self.published = 0
        self.start_time = time.monotonic()
        self.collect_events = True
        self.active = True

    def _event(self, name: str, event: Any) -> None:
        if self.collect_events:
            self.events[name].append({"t_s": time.monotonic() - self.start_time, **_event_payload(event)})

    def _on_timer(self) -> None:
        if not self.active:
            return
        elapsed = time.monotonic() - self.start_time
        pause_start = self.scenario.get("pause_start_s")
        pause_duration = float(self.scenario.get("pause_duration_s", 0.0))
        if pause_start is not None and float(pause_start) <= elapsed < float(pause_start) + pause_duration:
            return
        message = String()
        message.data = json.dumps(
            {
                "sequence": self.sequence,
                "send_monotonic_ns": time.monotonic_ns(),
                "payload": self.payload,
            },
            separators=(",", ":"),
        )
        self.publisher.publish(message)
        if _liveliness(self.scenario.get("liveliness")) == LivelinessPolicy.MANUAL_BY_TOPIC:
            try:
                self.publisher.assert_liveliness()
            except Exception:
                pass
        self.sequence += 1
        self.published += 1


class BenchmarkSubscriber(Node):
    def __init__(self, scenario: dict[str, Any], topic: str) -> None:
        super().__init__(f"ghost_g9_sub_{scenario['id']}")
        self.scenario = scenario
        self.collect_events = False
        self.start_time = 0.0
        self.received = 0
        self.bad_payloads = 0
        self.latency_ms: list[float] = []
        self.interarrival_ms: list[float] = []
        self.sequence_gaps = 0
        self.last_sequence: int | None = None
        self.last_receive_ns: int | None = None
        self.events: dict[str, list[dict[str, Any]]] = {
            "deadline": [],
            "liveliness": [],
            "message_lost": [],
            "incompatible_qos": [],
            "matched": [],
        }
        callbacks = SubscriptionEventCallbacks(
            deadline=lambda event: self._event("deadline", event),
            liveliness=lambda event: self._event("liveliness", event),
            message_lost=lambda event: self._event("message_lost", event),
            incompatible_qos=lambda event: self._event("incompatible_qos", event),
            matched=lambda event: self._event("matched", event),
            use_default_callbacks=False,
        )
        self.subscription = self.create_subscription(
            String,
            topic,
            self._on_message,
            build_qos(scenario, "subscriber"),
            event_callbacks=callbacks,
            callback_group=ReentrantCallbackGroup(),
        )

    def begin(self) -> None:
        self.start_time = time.monotonic()
        self.collect_events = True

    def _event(self, name: str, event: Any) -> None:
        if self.collect_events:
            self.events[name].append({"t_s": time.monotonic() - self.start_time, **_event_payload(event)})

    def _on_message(self, message: String) -> None:
        now_ns = time.monotonic_ns()
        try:
            payload = json.loads(message.data)
            sequence = int(payload["sequence"])
            send_ns = int(payload["send_monotonic_ns"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.bad_payloads += 1
            return
        if self.last_sequence is not None and sequence > self.last_sequence + 1:
            self.sequence_gaps += sequence - self.last_sequence - 1
        self.last_sequence = sequence
        if self.last_receive_ns is not None:
            self.interarrival_ms.append((now_ns - self.last_receive_ns) / 1.0e6)
        self.last_receive_ns = now_ns
        self.latency_ms.append(max(0.0, (now_ns - send_ns) / 1.0e6))
        self.received += 1
        delay_ms = float(self.scenario.get("subscriber_delay_ms", 0.0))
        if delay_ms > 0.0:
            time.sleep(delay_ms / 1000.0)


def run_qos_scenario(
    scenario: dict[str, Any],
    *,
    warmup_s: float,
    duration_s: float,
    payload_bytes: int,
    thermal_sample_hz: float,
    minimum_receive_fraction: float,
) -> dict[str, Any]:
    topic = f"/ghost/g9/{scenario['id']}"
    publisher = BenchmarkPublisher(scenario, topic, payload_bytes)
    subscriber = BenchmarkSubscriber(scenario, topic)
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(publisher)
    executor.add_node(subscriber)
    warmup_end = time.monotonic() + warmup_s
    while time.monotonic() < warmup_end:
        executor.spin_once(timeout_sec=0.02)
    offered_matches = publisher.publisher.get_subscription_count()
    requested_matches = subscriber.subscription.get_publisher_count()

    sampler = ResourceSampler(thermal_sample_hz)
    throttled_before = read_throttled_status()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    publisher.begin()
    subscriber.begin()
    sampler.start()
    workers = int(scenario.get("cpu_stress_workers", 0))
    with cpu_stress(workers):
        end = time.monotonic() + duration_s
        while time.monotonic() < end:
            executor.spin_once(timeout_sec=0.01)
        # Allow QoS event callbacks and final queued messages to drain.
        drain_end = time.monotonic() + 0.5
        while time.monotonic() < drain_end:
            executor.spin_once(timeout_sec=0.01)
    publisher.active = False
    publisher.collect_events = False
    subscriber.collect_events = False
    resources = sampler.stop()
    process_cpu_s = time.process_time() - cpu_start
    wall_s = time.perf_counter() - wall_start

    receive_fraction = subscriber.received / max(1, publisher.published)
    publication_rate_hz = publisher.published / max(wall_s, 1.0e-9)
    receive_rate_hz = subscriber.received / max(wall_s, 1.0e-9)
    deadline_ms = float(scenario.get("deadline_ms", 1000.0 / float(scenario["rate_hz"])))
    deadline_threshold_ms = max(deadline_ms * 1.5, 1.5 * 1000.0 / float(scenario["rate_hz"]))
    application_deadline_misses = sum(value > deadline_threshold_ms for value in subscriber.interarrival_ms)
    application_deadline_miss_fraction = application_deadline_misses / max(1, len(subscriber.interarrival_ms))
    lease_ms = scenario.get("liveliness_lease_ms")
    application_liveliness_gaps = (
        sum(value > float(lease_ms) for value in subscriber.interarrival_ms) if lease_ms is not None else 0
    )
    expected_compatible = bool(scenario.get("expected_compatible", True))
    incompatible_events = len(publisher.events["incompatible_qos"]) + len(subscriber.events["incompatible_qos"])
    deadline_events = len(publisher.events["deadline"]) + len(subscriber.events["deadline"])
    liveliness_events = len(publisher.events["liveliness"]) + len(subscriber.events["liveliness"])

    if expected_compatible:
        match_ok = offered_matches > 0 and requested_matches > 0 and subscriber.received > 0
        fraction_ok = bool(scenario.get("allow_receive_fraction_below_min", False)) or receive_fraction >= minimum_receive_fraction
        compatibility_ok = match_ok and fraction_ok
    else:
        graph_incompatibility_detected = (
            subscriber.received == 0 and offered_matches == 0 and requested_matches == 0
        )
        compatibility_ok = graph_incompatibility_detected
    pause_scenario = scenario.get("pause_duration_s") is not None
    deadline_detection_ok = True
    liveliness_detection_ok = True
    if pause_scenario:
        deadline_detection_ok = deadline_events > 0 or application_deadline_misses > 0
        liveliness_detection_ok = liveliness_events > 0 or application_liveliness_gaps > 0
    passed = compatibility_ok and deadline_detection_ok and liveliness_detection_ok and subscriber.bad_payloads == 0

    result = {
        "id": str(scenario["id"]),
        "expected_compatible": expected_compatible,
        "publisher_matches_after_warmup": offered_matches,
        "subscriber_matches_after_warmup": requested_matches,
        "published": publisher.published,
        "received": subscriber.received,
        "receive_fraction": receive_fraction,
        "publication_rate_hz": publication_rate_hz,
        "receive_rate_hz": receive_rate_hz,
        "sequence_gap_count": subscriber.sequence_gaps,
        "bad_payloads": subscriber.bad_payloads,
        "latency_ms": summarize_samples(subscriber.latency_ms),
        "interarrival_ms": summarize_samples(subscriber.interarrival_ms),
        "application_deadline_miss_count": application_deadline_misses,
        "application_deadline_miss_fraction": application_deadline_miss_fraction,
        "application_liveliness_gap_count": application_liveliness_gaps,
        "publisher_events": publisher.events,
        "subscriber_events": subscriber.events,
        "event_counts": {
            "deadline": deadline_events,
            "liveliness": liveliness_events,
            "incompatible_qos": incompatible_events,
            "message_lost": len(subscriber.events["message_lost"]),
            "matched": len(publisher.events["matched"]) + len(subscriber.events["matched"]),
        },
        "deadline_detection_ok": deadline_detection_ok,
        "liveliness_detection_ok": liveliness_detection_ok,
        "compatibility_ok": compatibility_ok,
        "incompatible_detection_basis": (
            "MIDDLEWARE_EVENT"
            if incompatible_events > 0
            else ("ROS_GRAPH_ZERO_MATCH_ZERO_DELIVERY" if not expected_compatible and compatibility_ok else None)
        ),
        "passed": passed,
        "wall_s": wall_s,
        "process_cpu_s": process_cpu_s,
        "process_cpu_fraction_of_one_core": process_cpu_s / wall_s if wall_s > 0.0 else None,
        "resource_summary": summarize_resources(resources),
        "throttled_before": throttled_before,
        "throttled_after": read_throttled_status(),
        "configuration": scenario,
    }
    executor.remove_node(publisher)
    executor.remove_node(subscriber)
    publisher.destroy_node()
    subscriber.destroy_node()
    executor.shutdown(timeout_sec=2.0)
    return result


def write_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "GHOST_X_G9_RUNTIME_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (out_dir / "GHOST_X_G9_RUNTIME_REPORT.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "scenario",
                "expected_compatible",
                "published",
                "received",
                "receive_fraction",
                "publication_rate_hz",
                "receive_rate_hz",
                "deadline_miss_fraction",
                "sequence_gaps",
                "latency_mean_ms",
                "latency_p99_ms",
                "latency_max_ms",
                "deadline_events",
                "liveliness_events",
                "incompatible_events",
                "max_temperature_c",
                "min_cpu_frequency_mhz",
                "passed",
            ]
        )
        for scenario in report["qos_scenarios"]:
            temperature = scenario["resource_summary"]["temperature_c"]
            frequency = scenario["resource_summary"]["cpu_frequency_mhz"]
            writer.writerow(
                [
                    scenario["id"],
                    scenario["expected_compatible"],
                    scenario["published"],
                    scenario["received"],
                    scenario["receive_fraction"],
                    scenario["publication_rate_hz"],
                    scenario["receive_rate_hz"],
                    scenario["application_deadline_miss_fraction"],
                    scenario["sequence_gap_count"],
                    scenario["latency_ms"]["mean"],
                    scenario["latency_ms"]["p99"],
                    scenario["latency_ms"]["max"],
                    scenario["event_counts"]["deadline"],
                    scenario["event_counts"]["liveliness"],
                    scenario["event_counts"]["incompatible_qos"],
                    temperature["max"],
                    frequency["min"],
                    scenario["passed"],
                ]
            )
    lines = [
        "# GHOST-X G9 DDS and Runtime Report",
        "",
        f"- RMW: `{report['environment']['rmw_implementation']}`",
        f"- QoS scenarios passed: `{report['qos_passed_count']}/{len(report['qos_scenarios'])}`",
        f"- Real-time claim status: `{report['real_time_claim_status']}`",
        "",
        "| Scenario | Pub | Rx | Receive | p99 latency (ms) | Max latency (ms) | Deadline events | Liveliness events | Result |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for scenario in report["qos_scenarios"]:
        p99 = scenario["latency_ms"]["p99"]
        maximum = scenario["latency_ms"]["max"]
        lines.append(
            f"| `{scenario['id']}` | {scenario['published']} | {scenario['received']} | {scenario['receive_fraction']:.3f} | "
            f"{'NA' if p99 is None else f'{p99:.3f}'} | {'NA' if maximum is None else f'{maximum:.3f}'} | "
            f"{scenario['event_counts']['deadline']} | {scenario['event_counts']['liveliness']} | {'PASS' if scenario['passed'] else 'FAIL'} |"
        )
    lines.extend(["", "## Predeclared runtime requirements", ""])
    lines.extend(["| Requirement | Result | Evidence summary |", "|---|---|---|"])
    for requirement_id, result in report.get("requirements", {}).items():
        lines.append(
            f"| `{requirement_id}` | {'PASS' if result.get('passed') else 'FAIL'} | {result.get('summary', '')} |"
        )
    lines.extend(
        [
            "",
            "## Estimator deadline",
            "",
            f"30 Hz deadline: `{report['estimator_deadline']['deadline_ms']:.3f} ms`",
            f"All observed maxima below deadline: `{report['estimator_deadline']['all_max_below_deadline']}`",
            "",
            "## Claim boundary",
            "",
            "This is Raspberry Pi bench and loopback DDS evidence. It does not establish operating-system hard-real-time guarantees, bounded network latency in flight, or flight qualification.",
            "",
        ]
    )
    (out_dir / "GHOST_X_G9_RUNTIME_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GHOST-X G9 runtime benchmarks.")
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--cpp-build-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--duration-scale", type=float, default=1.0)
    args = parser.parse_args()
    design = load_runtime_design(args.design)
    runtime = design["runtime"]
    scale = max(0.1, float(args.duration_scale))
    rclpy.init()
    try:
        qos_results = [
            run_qos_scenario(
                scenario,
                warmup_s=float(runtime["warmup_s"]) * scale,
                duration_s=float(scenario.get("duration_s", runtime["default_duration_s"])) * scale,
                payload_bytes=int(runtime["payload_bytes"]),
                thermal_sample_hz=float(runtime["thermal_sample_hz"]),
                minimum_receive_fraction=float(design["acceptance"]["compatible_min_receive_fraction"]),
            )
            for scenario in design["scenarios"]
        ]
        rmw = get_rmw_implementation_identifier()
    finally:
        rclpy.shutdown()

    stream = args.campaign_dir / "canonical_streams/g4_repeated_reentry_rep01.jsonl"
    cpp_cli = args.cpp_build_dir / "ghost_x_estimator_cli"
    cpp_config = PACKAGE_ROOT / "cpp/ghost_x_estimators/config/default_estimator.cfg"
    estimator_benchmarks = [
        benchmark_python_estimators(stream, repeats=6, stress_workers=0),
        benchmark_python_estimators(stream, repeats=4, stress_workers=2),
        benchmark_cpp_estimators(stream, cpp_cli, cpp_config, repeats=12, stress_workers=0),
        benchmark_cpp_estimators(stream, cpp_cli, cpp_config, repeats=8, stress_workers=2),
    ]
    deadline = evaluate_estimator_deadline(estimator_benchmarks, float(runtime["estimator_deadline_ms"]))
    qos_passed = sum(bool(result["passed"]) for result in qos_results)
    deadline_pause = next(result for result in qos_results if result["id"] == "reliable_deadline_liveliness_pause")
    incompatible = next(result for result in qos_results if result["id"] == "incompatible_best_effort_to_reliable")
    evidence_complete = (
        qos_passed == len(qos_results)
        and deadline_pause["deadline_detection_ok"]
        and deadline_pause["liveliness_detection_ok"]
        and incompatible["compatibility_ok"]
    )
    nominal_ids = {"best_effort_depth_1", "reliable_depth_10"}
    nominal = [result for result in qos_results if result["id"] in nominal_ids]
    nominal_latency_p95_ms = max(
        (float(result["latency_ms"]["p95"]) for result in nominal if result["latency_ms"]["p95"] is not None),
        default=float("inf"),
    )
    nominal_latency_p99_ms = max(
        (float(result["latency_ms"]["p99"]) for result in nominal if result["latency_ms"]["p99"] is not None),
        default=float("inf"),
    )
    nominal_sample_count = sum(int(result["latency_ms"]["count"]) for result in nominal)
    rt001_passed = (
        len(nominal) == 2
        and nominal_sample_count >= 30
        and nominal_latency_p95_ms <= 150.0
        and nominal_latency_p99_ms <= 250.0
    )
    estimator_30hz = next(result for result in qos_results if result["id"] == "reliable_estimator_30hz")
    rt002_passed = (
        estimator_30hz["publication_rate_hz"] >= 29.7
        and estimator_30hz["application_deadline_miss_fraction"] <= 0.01
        and estimator_30hz["interarrival_ms"]["p99"] is not None
    )
    throttling_clear = all(
        (result.get("throttled_before") in {None, "throttled=0x0"})
        and (result.get("throttled_after") in {None, "throttled=0x0"})
        for result in qos_results
    )
    thermal_samples = sum(int(result["resource_summary"]["temperature_c"]["count"]) for result in qos_results)
    rt003_passed = throttling_clear and thermal_samples > 0
    requirements = {
        "RT-001": {
            "passed": rt001_passed,
            "p95_ms": nominal_latency_p95_ms,
            "p99_ms": nominal_latency_p99_ms,
            "sample_count": nominal_sample_count,
            "limits_ms": {"p95": 150.0, "p99": 250.0},
            "summary": "Nominal source-to-receipt latency did not meet the predeclared bounds." if not rt001_passed else "Nominal latency met the predeclared bounds.",
        },
        "RT-002": {
            "passed": rt002_passed,
            "publication_rate_hz": estimator_30hz["publication_rate_hz"],
            "deadline_miss_fraction": estimator_30hz["application_deadline_miss_fraction"],
            "interarrival_ms": estimator_30hz["interarrival_ms"],
            "limits": {"minimum_rate_hz": 29.7, "maximum_deadline_miss_fraction": 0.01},
            "summary": "The 30 Hz publication/deadline requirement was not met on this bench run." if not rt002_passed else "The 30 Hz publication/deadline requirement was met on this bench run.",
        },
        "RT-003": {
            "passed": rt003_passed,
            "thermal_sample_count": thermal_samples,
            "throttling_clear": throttling_clear,
            "summary": "Resource and thermal evidence was collected without a reported throttling flag." if rt003_passed else "Resource or thermal evidence was incomplete or reported throttling.",
        },
    }
    requirements_all_passed = all(item["passed"] for item in requirements.values())
    real_time_status = (
        "BENCH_REQUIREMENTS_MET_NOT_HARD_REAL_TIME_CERTIFICATION"
        if deadline["all_max_below_deadline"] and evidence_complete and requirements_all_passed
        else "HARD_REAL_TIME_NOT_CLAIMED_REQUIREMENTS_NOT_MET"
    )
    report = {
        "schema_version": 1,
        "phase": "G9_DDS_AND_REAL_TIME",
        "passed": evidence_complete,
        "campaign_completed": evidence_complete,
        "requirements_all_passed": requirements_all_passed,
        "requirements": requirements,
        "qos_passed_count": qos_passed,
        "qos_scenarios": qos_results,
        "estimator_benchmarks": estimator_benchmarks,
        "estimator_deadline": deadline,
        "real_time_claim_status": real_time_status,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "ros_distro": os.environ.get("ROS_DISTRO"),
            "rmw_implementation": rmw,
            "cpu_count": os.cpu_count(),
            "max_process_rss_mb": max_rss_mb(),
            "throttled_status_final": read_throttled_status(),
        },
        "claim_boundary": "BENCH_AND_LOOPBACK_DDS_EVIDENCE_NOT_FLIGHT_HARD_REAL_TIME_CERTIFICATION",
        "reference_basis": "ROS 2 Jazzy QoS policies: history/depth, reliability, deadline, liveliness, lease duration, and compatibility.",
    }
    write_outputs(report, args.out_dir)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "qos_passed": qos_passed,
                "qos_total": len(qos_results),
                "real_time_claim_status": real_time_status,
            },
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
