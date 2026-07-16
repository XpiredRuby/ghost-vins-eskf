#!/usr/bin/env python3
"""Capture and schema-validate live GHOST-X G2 JSON topics."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost_sim_ros2.data_contract import canonical_sha256, validate_payload


TOPICS = {
    "/ghost/tracker_imm/futures_json": "formal_imm_futures.schema.json",
    "/ghost/tracker_mh/futures_json": "ghost_mh_futures.schema.json",
    "/ghost/tracker_imm/status_json": "tracker_status.schema.json",
    "/ghost/tracker_mh/status_json": "tracker_status.schema.json",
    "/ghost/evaluation/status_json": "mission_validation.schema.json",
}


class ContractProbe(Node):
    def __init__(self, schema_dir: Path) -> None:
        super().__init__("ghost_x_g2_contract_probe")
        self.schema_dir = schema_dir
        self.results: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []
        for topic, schema_name in TOPICS.items():
            self.create_subscription(
                String,
                topic,
                lambda msg, topic=topic, schema_name=schema_name: self.on_payload(
                    topic, schema_name, msg
                ),
                10,
            )

    def on_payload(self, topic: str, schema_name: str, msg: String) -> None:
        if topic in self.results:
            return
        try:
            payload = json.loads(msg.data)
            validate_payload(payload, schema_name, self.schema_dir)
        except Exception as exc:  # report exact runtime contract failure
            self.errors.append(f"{topic}: {type(exc).__name__}: {exc}")
            return
        self.results[topic] = {
            "schema": schema_name,
            "payload_sha256": canonical_sha256(payload),
            "schema_version": payload.get("schema_version"),
            "contract_version": payload.get("contract_version"),
            "tracker": payload.get("tracker"),
            "frame_id": payload.get("frame_id"),
            "provenance": payload.get("provenance"),
            "timestamps": payload.get("timestamps"),
            "validity": payload.get("validity"),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout-s", type=float, default=20.0)
    args = parser.parse_args()

    rclpy.init()
    node = ContractProbe(args.schema_dir)
    deadline = time.monotonic() + max(1.0, args.timeout_s)
    try:
        while time.monotonic() < deadline and len(node.results) < len(TOPICS):
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    missing = sorted(set(TOPICS) - set(node.results))
    report = {
        "schema_version": 1,
        "phase": "G2_RUNTIME_CONTRACT_PROBE",
        "passed": not node.errors and not missing,
        "expected_topics": sorted(TOPICS),
        "validated_topics": sorted(node.results),
        "missing_topics": missing,
        "errors": node.errors,
        "results": node.results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "validated": len(node.results),
        "expected": len(TOPICS),
        "missing": missing,
        "errors": node.errors,
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
