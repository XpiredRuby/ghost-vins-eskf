import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>GHOST-MH Visual Dashboard</title>
  <style>
    body { margin: 0; background: #0b0f14; color: #e8eef5; font-family: Arial, sans-serif; }
    header { padding: 14px 18px; background: #111821; border-bottom: 1px solid #263241; }
    h1 { margin: 0; font-size: 22px; }
    .sub { color: #9fb0c3; margin-top: 4px; font-size: 13px; }
    main { display: grid; grid-template-columns: 1fr 380px; gap: 14px; padding: 14px; }
    canvas { width: 100%; height: calc(100vh - 120px); background: #071018; border: 1px solid #27384a; border-radius: 10px; }
    .panel { background: #101822; border: 1px solid #27384a; border-radius: 10px; padding: 14px; }
    .big { font-size: 22px; font-weight: bold; margin-bottom: 8px; }
    .good { color: #65e29c; }
    .warn { color: #ffd166; }
    .bad { color: #ff6b6b; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid #223040; }
    th { color: #9fb0c3; }
    .math { font-family: Consolas, monospace; font-size: 12px; color: #c7d4e2; line-height: 1.45; }
    .small { color: #9fb0c3; font-size: 12px; line-height: 1.4; }
  </style>
</head>
<body>
  <header>
    <h1>GHOST-MH Visual Dashboard</h1>
    <div class="sub">Top-down probability map from live AprilTag measurements and physics-mode hypotheses</div>
  </header>
  <main>
    <canvas id="map" width="1100" height="760"></canvas>
    <section class="panel">
      <div id="status" class="big">WAITING</div>
      <div id="meta" class="small"></div>
      <h3>Top futures</h3>
      <table>
        <thead><tr><th>#</th><th>model</th><th>prob</th><th>x,y</th></tr></thead>
        <tbody id="futureRows"></tbody>
      </table>
      <h3>Evidence model</h3>
      <div class="math">
        state = [x, y, vx, vy]<br>
        predict: xₖ₊₁ = F xₖ + physics_mode<br>
        update: weight ∝ prior × Gaussian likelihood<br>
        likelihood uses measurement residual and covariance<br>
        occlusion: branch into physically plausible futures<br>
        safety: stop after max occlusion horizon
      </div>
      <p class="small">
        The percentages are posterior belief weights over motion hypotheses, not magic certainty.
        They come from recent visual evidence, calibrated mode priors, motion physics, measurement noise,
        and Bayesian likelihood scoring.
      </p>
    </section>
  </main>
<script>
const canvas = document.getElementById('map');
const ctx = canvas.getContext('2d');
const rows = document.getElementById('futureRows');
const statusEl = document.getElementById('status');
const metaEl = document.getElementById('meta');
const palette = ['#4cc9f0','#f72585','#b8f35a','#ffd166','#c77dff','#ff9f1c','#90dbf4'];
let latest = null;

function finite(v, fallback=0) { return Number.isFinite(v) ? v : fallback; }
function fmt(v, n=3) { return Number.isFinite(v) ? v.toFixed(n) : 'nan'; }

function collectPoints(payload) {
  const pts = [];
  if (!payload) return pts;
  if (payload.estimate) pts.push([payload.estimate.x_m, payload.estimate.y_m]);
  for (const h of (payload.hypotheses || [])) {
    pts.push([h.x_m, h.y_m]);
    for (const p of (h.path || [])) pts.push([p.x_m, p.y_m]);
  }
  return pts;
}

function makeTransform(payload) {
  const pts = collectPoints(payload);
  let maxX = 0.8;
  let maxAbsY = 0.35;
  for (const [x, y] of pts) {
    if (Number.isFinite(x)) maxX = Math.max(maxX, x + 0.2);
    if (Number.isFinite(y)) maxAbsY = Math.max(maxAbsY, Math.abs(y) + 0.15);
  }
  const pad = 58;
  const sx = (canvas.width - 2*pad) / (2 * maxAbsY);
  const sy = (canvas.height - 2*pad) / maxX;
  const scale = Math.min(sx, sy);
  return {pad, scale, maxX, maxAbsY, cx: canvas.width/2, bottom: canvas.height - pad};
}

function toCanvas(t, x, y) {
  return {
    px: t.cx + y * t.scale,
    py: t.bottom - x * t.scale
  };
}

function drawGrid(t) {
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle = '#071018';
  ctx.fillRect(0,0,canvas.width,canvas.height);

  ctx.strokeStyle = '#1c2a38';
  ctx.lineWidth = 1;
  ctx.font = '13px Arial';
  ctx.fillStyle = '#7890a8';

  for (let x=0; x<=t.maxX+0.001; x+=0.1) {
    const a = toCanvas(t, x, -t.maxAbsY);
    const b = toCanvas(t, x, t.maxAbsY);
    ctx.beginPath(); ctx.moveTo(a.px,a.py); ctx.lineTo(b.px,b.py); ctx.stroke();
    if (Math.abs((x*10)%5) < 0.01) ctx.fillText(`${x.toFixed(1)}m`, 8, a.py+4);
  }
  for (let y=-t.maxAbsY; y<=t.maxAbsY+0.001; y+=0.1) {
    const a = toCanvas(t, 0, y);
    const b = toCanvas(t, t.maxX, y);
    ctx.beginPath(); ctx.moveTo(a.px,a.py); ctx.lineTo(b.px,b.py); ctx.stroke();
  }

  const origin = toCanvas(t, 0, 0);
  const forward = toCanvas(t, t.maxX, 0);
  ctx.strokeStyle = '#5b7088'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(origin.px, origin.py); ctx.lineTo(forward.px, forward.py); ctx.stroke();
  ctx.fillStyle = '#b7c8da';
  ctx.fillText('camera', origin.px + 8, origin.py - 8);
  ctx.fillText('forward range x', forward.px + 8, forward.py + 14);
  ctx.fillText('lateral y', canvas.width - 110, origin.py - 8);
}

function drawPath(t, hyp, color, rank) {
  const path = hyp.path || [];
  if (path.length < 1) return;
  const prob = Math.max(0.02, Math.min(1.0, hyp.probability || 0));
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.22 + 0.78 * prob;
  ctx.lineWidth = 2 + 8 * prob;
  ctx.beginPath();
  for (let i=0; i<path.length; i++) {
    const p = toCanvas(t, path[i].x_m, path[i].y_m);
    if (i === 0) ctx.moveTo(p.px, p.py); else ctx.lineTo(p.px, p.py);
  }
  ctx.stroke();
  const end = toCanvas(t, path[path.length-1].x_m, path[path.length-1].y_m);
  ctx.beginPath(); ctx.arc(end.px, end.py, 5 + 7*prob, 0, Math.PI*2); ctx.fill();
  ctx.globalAlpha = 1.0;
  ctx.font = 'bold 15px Arial';
  ctx.fillText(`${rank}: ${Math.round(prob*100)}%`, end.px + 10, end.py - 8);
  ctx.restore();
}

function drawEstimate(t, estimate) {
  if (!estimate) return;
  const p = toCanvas(t, estimate.x_m, estimate.y_m);
  ctx.fillStyle = '#ffffff';
  ctx.beginPath(); ctx.arc(p.px, p.py, 8, 0, Math.PI*2); ctx.fill();
  ctx.strokeStyle = '#111'; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = '#ffffff'; ctx.font = 'bold 14px Arial';
  ctx.fillText('estimate', p.px + 12, p.py + 4);
}

function render(payload) {
  latest = payload;
  const t = makeTransform(payload);
  drawGrid(t);

  const hyps = (payload && payload.hypotheses) ? payload.hypotheses : [];
  hyps.slice(0,7).forEach((h, i) => drawPath(t, h, palette[i % palette.length], i+1));
  if (payload && payload.estimate) drawEstimate(t, payload.estimate);

  const visible = payload && payload.visible;
  const initialized = payload && payload.initialized;
  const age = payload ? payload.measurement_age_s : null;
  statusEl.textContent = initialized ? (visible ? 'VISIBLE' : 'OCCLUDED / PREDICTING') : 'WAITING FOR TARGET';
  statusEl.className = 'big ' + (initialized ? (visible ? 'good' : 'warn') : 'bad');
  metaEl.innerHTML = `initialized: ${initialized}<br>measurement age: ${age === null ? 'none' : fmt(age,2)+' s'}<br>hypotheses: ${hyps.length}`;

  rows.innerHTML = '';
  for (const h of hyps.slice(0,5)) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${h.rank}</td><td>${h.model}</td><td>${fmt(100*h.probability,1)}%</td><td>${fmt(h.x_m,2)}, ${fmt(h.y_m,2)}</td>`;
    rows.appendChild(tr);
  }
}

async function poll() {
  try {
    const r = await fetch('/api/state', {cache:'no-store'});
    const d = await r.json();
    render(d.payload || {});
  } catch (e) {
    statusEl.textContent = 'DASHBOARD DISCONNECTED';
    statusEl.className = 'big bad';
  }
}
setInterval(poll, 200);
poll();
</script>
</body>
</html>
"""


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.status = "NO_STATUS_YET"
        self.payload: dict[str, Any] | None = None
        self.status_time = 0.0
        self.payload_time = 0.0

    def set_status(self, status: str) -> None:
        with self.lock:
            self.status = status
            self.status_time = time.time()

    def set_payload(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.payload = payload
            self.payload_time = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "status": self.status,
                "payload": self.payload,
                "status_age_s": None if self.status_time == 0.0 else time.time() - self.status_time,
                "payload_age_s": None if self.payload_time == 0.0 else time.time() - self.payload_time,
            }


class DashboardHandler(BaseHTTPRequestHandler):
    state: SharedState

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/index"):
            self.send_text(HTML, "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/state"):
            self.send_text(json.dumps(self.state.snapshot()), "application/json")
            return
        self.send_response(404)
        self.end_headers()

    def send_text(self, text: str, content_type: str) -> None:
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


class GhostMHWebDashboard(Node):
    def __init__(self) -> None:
        super().__init__("ghost_mh_web_dashboard")
        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 8090)
        self.declare_parameter("status_topic", "/ghost/tracker_mh/status")
        self.declare_parameter("futures_topic", "/ghost/tracker_mh/futures_json")

        self.state = SharedState()
        self.create_subscription(String, str(self.get_parameter("status_topic").value), self.on_status, 10)
        self.create_subscription(String, str(self.get_parameter("futures_topic").value), self.on_futures, 10)

        host = str(self.get_parameter("host").value)
        port = int(self.get_parameter("port").value)
        DashboardHandler.state = self.state
        self.server = ThreadingHTTPServer((host, port), DashboardHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.get_logger().info(f"GHOST-MH visual dashboard open on http://{host}:{port}")

    def on_status(self, msg: String) -> None:
        self.state.set_status(msg.data)

    def on_futures(self, msg: String) -> None:
        try:
            self.state.set_payload(json.loads(msg.data))
        except json.JSONDecodeError:
            self.state.set_payload({"initialized": False, "visible": False, "error": "bad JSON"})

    def destroy_node(self) -> bool:
        try:
            self.server.shutdown()
            self.server.server_close()
        finally:
            return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = GhostMHWebDashboard()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
