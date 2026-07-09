import json
import os
import time
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class GhostMHMonitor(Node):
    """Readable terminal monitor for the live GHOST-MH tracker."""

    def __init__(self) -> None:
        super().__init__("ghost_mh_monitor")
        self.declare_parameter("status_topic", "/ghost/tracker_mh/status")
        self.declare_parameter("futures_topic", "/ghost/tracker_mh/futures_json")
        self.declare_parameter("refresh_hz", 2.0)

        self.status_topic = str(self.get_parameter("status_topic").value)
        self.futures_topic = str(self.get_parameter("futures_topic").value)
        self.refresh_hz = float(self.get_parameter("refresh_hz").value)

        self.latest_status: str = "NO_STATUS_YET"
        self.latest_payload: dict[str, Any] | None = None
        self.latest_status_time = 0.0
        self.latest_payload_time = 0.0

        self.create_subscription(String, self.status_topic, self.on_status, 10)
        self.create_subscription(String, self.futures_topic, self.on_futures, 10)
        self.create_timer(1.0 / max(self.refresh_hz, 0.2), self.render)

    def on_status(self, msg: String) -> None:
        self.latest_status = msg.data
        self.latest_status_time = time.time()

    def on_futures(self, msg: String) -> None:
        try:
            self.latest_payload = json.loads(msg.data)
            self.latest_payload_time = time.time()
        except json.JSONDecodeError:
            self.latest_payload = {"error": "bad json", "raw": msg.data[:200]}
            self.latest_payload_time = time.time()

    def render(self) -> None:
        os.system("clear")
        now = time.time()
        print("GHOST-MH LIVE MONITOR")
        print("=====================")
        print(f"status topic:  {self.status_topic}")
        print(f"futures topic: {self.futures_topic}")
        print()
        print(f"STATUS: {self.latest_status}")
        if self.latest_status_time > 0.0:
            print(f"status age: {now - self.latest_status_time:.2f}s")
        else:
            print("status age: never received")

        payload = self.latest_payload
        if not payload:
            print()
            print("No futures JSON received yet.")
            return

        print()
        print("TRACKER")
        print("-------")
        print(f"visible:          {payload.get('visible')}")
        print(f"initialized:      {payload.get('initialized')}")
        print(f"measurement age:  {payload.get('measurement_age_s')}")
        print(f"payload age:      {now - self.latest_payload_time:.2f}s")

        estimate = payload.get("estimate")
        if estimate:
            print()
            print("ESTIMATE")
            print("--------")
            print(
                "x={x:.3f} m  y={y:.3f} m  vx={vx:.3f} m/s  vy={vy:.3f} m/s".format(
                    x=float(estimate.get("x_m", 0.0)),
                    y=float(estimate.get("y_m", 0.0)),
                    vx=float(estimate.get("vx_mps", 0.0)),
                    vy=float(estimate.get("vy_mps", 0.0)),
                )
            )

        hypotheses = payload.get("hypotheses") or []
        print()
        print("TOP FUTURES")
        print("-----------")
        if not hypotheses:
            print("none")
            return

        for hyp in hypotheses[:5]:
            rank = int(hyp.get("rank", 0))
            model = str(hyp.get("model", "unknown"))
            weight = 100.0 * float(hyp.get("relative_hypothesis_weight", hyp.get("probability", 0.0)))
            x = float(hyp.get("x_m", 0.0))
            y = float(hyp.get("y_m", 0.0))
            vx = float(hyp.get("vx_mps", 0.0))
            vy = float(hyp.get("vy_mps", 0.0))
            print(f"{rank}. {model:<24} {weight:6.2f}% weight  x={x: .3f} y={y: .3f}  vx={vx: .3f} vy={vy: .3f}")


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = GhostMHMonitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
