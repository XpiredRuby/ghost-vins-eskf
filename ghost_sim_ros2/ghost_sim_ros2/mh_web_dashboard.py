import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String


HTML_TEMPLATE = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GHOST Operator Console</title>
  <style>
    :root {
      --bg:#070b10; --card:#0f1722; --card2:#111d2a; --line:#26384c;
      --text:#edf5ff; --muted:#9fb2c8; --green:#55e39a; --yellow:#ffd166;
      --red:#ff6b6b; --blue:#4cc9f0; --violet:#c77dff;
    }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:Inter, Arial, sans-serif; overflow:hidden; }
    header { height:64px; display:flex; align-items:center; justify-content:space-between; padding:10px 16px; background:#0e1621; border-bottom:1px solid var(--line); }
    .brand h1 { margin:0; font-size:21px; letter-spacing:0.5px; }
    .brand .sub { color:var(--muted); margin-top:3px; font-size:12.5px; }
    .badge { border:1px solid #36506b; border-radius:999px; padding:5px 10px; color:#b8cce1; font-size:12px; background:#0b121b; }
    main { height:calc(100vh - 64px); display:grid; grid-template-columns:minmax(0,1fr) 405px; gap:10px; padding:10px; }
    .left { min-width:0; min-height:0; display:grid; grid-template-rows:42% 58%; gap:10px; }
    .card { min-height:0; overflow:hidden; background:linear-gradient(180deg,var(--card2),var(--card)); border:1px solid var(--line); border-radius:12px; box-shadow:0 10px 28px rgba(0,0,0,0.23); }
    .card-title { height:38px; padding:9px 12px; border-bottom:1px solid #223247; color:#cbd9e8; font-size:13.5px; font-weight:700; display:flex; justify-content:space-between; align-items:center; }
    .camera-frame { width:100%; height:calc(100% - 38px); border:0; background:#000; display:block; }
    canvas { width:100%; height:calc(100% - 38px); background:#071018; display:block; }
    .panel { padding:12px; overflow:auto; }
    .state { font-size:24px; font-weight:800; margin:2px 0 10px; letter-spacing:0.3px; }
    .good { color:var(--green); } .warn { color:var(--yellow); } .bad { color:var(--red); }
    .kpis { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px; }
    .kpi { background:#0b121b; border:1px solid #203247; border-radius:10px; padding:8px; }
    .kpi label { display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:0.7px; }
    .kpi strong { display:block; margin-top:4px; font-size:16px; }
    h3 { margin:14px 0 8px; font-size:15px; }
    table { width:100%; border-collapse:collapse; font-size:12.5px; }
    th,td { text-align:left; padding:6px 4px; border-bottom:1px solid #223040; vertical-align:middle; }
    th { color:var(--muted); font-weight:700; }
    .bar { position:relative; height:8px; width:70px; border-radius:999px; background:#1a2736; overflow:hidden; margin-top:3px; }
    .bar span { position:absolute; left:0; top:0; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--blue),var(--violet)); }
    .model { max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .math { font-family:Consolas, monospace; font-size:12px; color:#c7d4e2; line-height:1.5; background:#0b121b; border:1px solid #203247; border-radius:10px; padding:10px; }
    .small { color:var(--muted); font-size:12px; line-height:1.45; }
    .pill { font-size:11.5px; border:1px solid #34485e; border-radius:999px; padding:3px 8px; color:var(--muted); background:#0b121b; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>GHOST Operator Console</h1>
      <div class="sub">GPS-denied probabilistic tracker · camera evidence + physics hypotheses</div>
    </div>
    <div class="badge" id="clock">SYSTEM LIVE</div>
  </header>
  <main>
    <section class="left">
      <div class="card">
        <div class="card-title"><span>Live camera / AprilTag evidence</span><span class="pill">visual source</span></div>
        <iframe class="camera-frame" src="__CAMERA_URL__"></iframe>
      </div>
      <div class="card">
        <div class="card-title"><span>Probabilistic future map</span><span class="pill">2-sigma covariance shown</span></div>
        <canvas id="map"></canvas>
      </div>
    </section>
    <section class="card panel">
      <div id="status" class="state bad">WAITING</div>
      <div class="kpis">
        <div class="kpi"><label>Measurement age</label><strong id="measAge">--</strong></div>
        <div class="kpi"><label>Payload age</label><strong id="payloadAge">--</strong></div>
        <div class="kpi"><label>Browser RTT</label><strong id="rtt">--</strong></div>
        <div class="kpi"><label>Hypotheses</label><strong id="hypCount">--</strong></div>
        <div class="kpi"><label>Tracker tick</label><strong id="tickHz">--</strong></div>
        <div class="kpi"><label>Measurements</label><strong id="measCount">--</strong></div>
      </div>
      <div id="meta" class="small"></div>
      <h3>Ranked future hypotheses</h3>
      <table>
        <thead><tr><th>#</th><th>model</th><th>probability</th><th>x,y m</th></tr></thead>
        <tbody id="futureRows"></tbody>
      </table>
      <h3>Math contract</h3>
      <div class="math">
        state = [x, y, vx, vy]<br>
        predict: x(k+1) = F x(k) + physics_mode<br>
        posterior ∝ prior × Gaussian likelihood(residual, covariance)<br>
        uncertainty grows during occlusion; no hidden measurement is invented<br>
        bounded horizon prevents infinite hallucination
      </div>
      <p class="small">
        Precision target is handled by measurement calibration, latency reduction, covariance display,
        and validation logs. Occluded tracking is probabilistic, not absolute ground truth.
      </p>
    </section>
  </main>
<script>
const POLL_MS = __POLL_MS__;
const canvas = document.getElementById('map');
const ctx = canvas.getContext('2d');
const rows = document.getElementById('futureRows');
const statusEl = document.getElementById('status');
const metaEl = document.getElementById('meta');
const measAgeEl = document.getElementById('measAge');
const payloadAgeEl = document.getElementById('payloadAge');
const rttEl = document.getElementById('rtt');
const hypCountEl = document.getElementById('hypCount');
const tickHzEl = document.getElementById('tickHz');
const measCountEl = document.getElementById('measCount');
const clockEl = document.getElementById('clock');
const palette = ['#4cc9f0','#f72585','#b8f35a','#ffd166','#c77dff','#ff9f1c','#90dbf4'];
let lastState = {};
let lastRttMs = NaN;

function fmt(v,n=3){ return Number.isFinite(v) ? v.toFixed(n) : '--'; }
function ms(v){ return Number.isFinite(v) ? `${(1000*v).toFixed(0)} ms` : '--'; }
function pct(v){ return Number.isFinite(v) ? `${(100*v).toFixed(1)}%` : '--'; }
function fitCanvas(){ const r=canvas.getBoundingClientRect(), dpr=window.devicePixelRatio||1; const w=Math.max(400,Math.floor(r.width*dpr)); const h=Math.max(260,Math.floor(r.height*dpr)); if(canvas.width!==w||canvas.height!==h){canvas.width=w; canvas.height=h;} }
function collectPoints(payload){ const pts=[]; if(!payload)return pts; if(payload.estimate)pts.push([payload.estimate.x_m,payload.estimate.y_m]); for(const h of (payload.hypotheses||[])){pts.push([h.x_m,h.y_m]); for(const p of (h.path||[]))pts.push([p.x_m,p.y_m]);} return pts; }
function makeTransform(payload){ const pts=collectPoints(payload); let maxX=0.8,maxAbsY=0.35; for(const [x,y] of pts){ if(Number.isFinite(x))maxX=Math.max(maxX,x+0.2); if(Number.isFinite(y))maxAbsY=Math.max(maxAbsY,Math.abs(y)+0.15); } const pad=46; const sx=(canvas.width-2*pad)/(2*maxAbsY); const sy=(canvas.height-2*pad)/maxX; return {pad,scale:Math.min(sx,sy),maxX,maxAbsY,cx:canvas.width/2,bottom:canvas.height-pad}; }
function toCanvas(t,x,y){ return {px:t.cx+y*t.scale, py:t.bottom-x*t.scale}; }
function drawGrid(t){ ctx.clearRect(0,0,canvas.width,canvas.height); ctx.fillStyle='#071018'; ctx.fillRect(0,0,canvas.width,canvas.height); ctx.strokeStyle='#1c2a38'; ctx.lineWidth=1; ctx.font='13px Arial'; ctx.fillStyle='#7890a8'; for(let x=0;x<=t.maxX+1e-3;x+=0.1){ const a=toCanvas(t,x,-t.maxAbsY), b=toCanvas(t,x,t.maxAbsY); ctx.beginPath(); ctx.moveTo(a.px,a.py); ctx.lineTo(b.px,b.py); ctx.stroke(); if(Math.abs((x*10)%5)<0.01)ctx.fillText(`${x.toFixed(1)}m`,8,a.py+4); } for(let y=-t.maxAbsY;y<=t.maxAbsY+1e-3;y+=0.1){ const a=toCanvas(t,0,y), b=toCanvas(t,t.maxX,y); ctx.beginPath(); ctx.moveTo(a.px,a.py); ctx.lineTo(b.px,b.py); ctx.stroke(); } const o=toCanvas(t,0,0), f=toCanvas(t,t.maxX,0); ctx.strokeStyle='#5b7088'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(o.px,o.py); ctx.lineTo(f.px,f.py); ctx.stroke(); ctx.fillStyle='#b7c8da'; ctx.fillText('camera origin',o.px+8,o.py-8); ctx.fillText('forward x',f.px+8,f.py+14); }
function drawEllipse(t,obj,color,alpha){ const cxx=Number(obj.cov_xx), cxy=Number(obj.cov_xy), cyy=Number(obj.cov_yy); if(!Number.isFinite(cxx)||!Number.isFinite(cxy)||!Number.isFinite(cyy))return; const tr=cxx+cyy; const disc=Math.sqrt(Math.max(0,(cxx-cyy)*(cxx-cyy)+4*cxy*cxy)); const l1=Math.max(0,(tr+disc)/2), l2=Math.max(0,(tr-disc)/2); const angle=0.5*Math.atan2(2*cxy,cxx-cyy); const p=toCanvas(t,obj.x_m,obj.y_m); const r1=Math.max(2,2*Math.sqrt(l1)*t.scale), r2=Math.max(2,2*Math.sqrt(l2)*t.scale); ctx.save(); ctx.translate(p.px,p.py); ctx.rotate(-angle); ctx.strokeStyle=color; ctx.globalAlpha=alpha; ctx.lineWidth=1.5; ctx.beginPath(); ctx.ellipse(0,0,r2,r1,0,0,Math.PI*2); ctx.stroke(); ctx.restore(); ctx.globalAlpha=1; }
function drawVelocity(t,obj,color){ if(!obj)return; const p=toCanvas(t,obj.x_m,obj.y_m); const q=toCanvas(t,obj.x_m+0.20*obj.vx_mps,obj.y_m+0.20*obj.vy_mps); ctx.strokeStyle=color; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(p.px,p.py); ctx.lineTo(q.px,q.py); ctx.stroke(); }
function drawPath(t,h,color,rank){ const path=h.path||[]; if(path.length<1)return; const prob=Math.max(0.02,Math.min(1,h.probability||0)); ctx.save(); ctx.strokeStyle=color; ctx.fillStyle=color; ctx.globalAlpha=0.20+0.80*prob; ctx.lineWidth=2+7*prob; ctx.beginPath(); for(let i=0;i<path.length;i++){ const p=toCanvas(t,path[i].x_m,path[i].y_m); if(i===0)ctx.moveTo(p.px,p.py); else ctx.lineTo(p.px,p.py); } ctx.stroke(); const end=toCanvas(t,path[path.length-1].x_m,path[path.length-1].y_m); ctx.beginPath(); ctx.arc(end.px,end.py,5+7*prob,0,Math.PI*2); ctx.fill(); ctx.globalAlpha=1; ctx.font='bold 14px Arial'; ctx.fillText(`${rank}: ${Math.round(prob*100)}%`,end.px+10,end.py-8); ctx.restore(); drawEllipse(t,h,color,0.32); }
function drawEstimate(t,e){ if(!e)return; drawEllipse(t,e,'#ffffff',0.45); const p=toCanvas(t,e.x_m,e.y_m); ctx.fillStyle='#ffffff'; ctx.beginPath(); ctx.arc(p.px,p.py,7,0,Math.PI*2); ctx.fill(); ctx.strokeStyle='#000'; ctx.lineWidth=2; ctx.stroke(); ctx.fillStyle='#ffffff'; ctx.font='bold 13px Arial'; ctx.fillText('estimate',p.px+11,p.py+4); drawVelocity(t,e,'#ffffff'); }
function render(state){ lastState=state||{}; const payload=lastState.payload||{}; fitCanvas(); const t=makeTransform(payload); drawGrid(t); const hyps=payload.hypotheses||[]; hyps.slice(0,7).forEach((h,i)=>drawPath(t,h,palette[i%palette.length],i+1)); drawEstimate(t,payload.estimate); const initialized=!!payload.initialized, visible=!!payload.visible; statusEl.textContent=initialized?(visible?'VISIBLE - MEASUREMENT LOCK':'OCCLUDED - PREDICTING'):'WAITING FOR TARGET'; statusEl.className='state '+(initialized?(visible?'good':'warn'):'bad'); measAgeEl.textContent=ms(payload.measurement_age_s); payloadAgeEl.textContent=ms(lastState.payload_age_s); rttEl.textContent=Number.isFinite(lastRttMs)?`${lastRttMs.toFixed(0)} ms`:'--'; hypCountEl.textContent=hyps.length; tickHzEl.textContent=payload.tick_hz?`${fmt(payload.tick_hz,0)} Hz`:'--'; measCountEl.textContent=payload.measurement_count ?? '--'; metaEl.innerHTML=`frame: ${payload.frame_id||'--'} · seq: ${payload.sequence??'--'} · future horizon: ${fmt(payload.future_horizon_s,1)} s · dt: ${fmt(payload.future_dt_s,2)} s`; rows.innerHTML=''; for(const h of hyps.slice(0,5)){ const tr=document.createElement('tr'); const p=Math.max(0,Math.min(100,100*(h.probability||0))); tr.innerHTML=`<td>${h.rank}</td><td class="model">${h.model}</td><td><b>${pct(h.probability)}</b><div class="bar"><span style="width:${p}%"></span></div></td><td>${fmt(h.x_m,2)}, ${fmt(h.y_m,2)}</td>`; rows.appendChild(tr); } clockEl.textContent=`poll ${POLL_MS} ms · ${new Date().toLocaleTimeString()}`; }
async function pollLoop(){ const t0=performance.now(); try{ const r=await fetch(`/api/state?t=${Date.now()}`,{cache:'no-store'}); const d=await r.json(); lastRttMs=performance.now()-t0; render(d); } catch(e){ statusEl.textContent='DASHBOARD DISCONNECTED'; statusEl.className='state bad'; } setTimeout(pollLoop,POLL_MS); }
window.addEventListener('resize',()=>render(lastState));
pollLoop();
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
        self.payload_seq = 0

    def set_status(self, status: str) -> None:
        with self.lock:
            self.status = status
            self.status_time = time.time()

    def set_payload(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.payload = payload
            self.payload_time = time.time()
            self.payload_seq += 1

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self.lock:
            return {
                "server_time_s": now,
                "status": self.status,
                "payload": self.payload,
                "payload_seq": self.payload_seq,
                "status_age_s": None if self.status_time == 0.0 else now - self.status_time,
                "payload_age_s": None if self.payload_time == 0.0 else now - self.payload_time,
            }


class DashboardHandler(BaseHTTPRequestHandler):
    state: SharedState
    camera_url: str = "http://192.168.1.142:8081"
    poll_ms: int = 50

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/index"):
            html = HTML_TEMPLATE.replace("__CAMERA_URL__", self.camera_url).replace("__POLL_MS__", str(self.poll_ms))
            self.send_text(html, "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/state"):
            self.send_text(json.dumps(self.state.snapshot(), separators=(",", ":")), "application/json")
            return
        if self.path.startswith("/api/health"):
            self.send_text(json.dumps({"ok": True, "time_s": time.time()}), "application/json")
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
        self.declare_parameter("camera_url", "http://192.168.1.142:8081")
        self.declare_parameter("poll_ms", 50)
        self.declare_parameter("status_topic", "/ghost/tracker_mh/status")
        self.declare_parameter("futures_topic", "/ghost/tracker_mh/futures_json")

        self.state = SharedState()
        qos = QoSProfile(depth=1)
        self.create_subscription(String, str(self.get_parameter("status_topic").value), self.on_status, qos)
        self.create_subscription(String, str(self.get_parameter("futures_topic").value), self.on_futures, qos)

        host = str(self.get_parameter("host").value)
        port = int(self.get_parameter("port").value)
        DashboardHandler.state = self.state
        DashboardHandler.camera_url = str(self.get_parameter("camera_url").value)
        DashboardHandler.poll_ms = int(self.get_parameter("poll_ms").value)
        self.server = ThreadingHTTPServer((host, port), DashboardHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.get_logger().info(f"GHOST operator dashboard open on http://{host}:{port}")

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
