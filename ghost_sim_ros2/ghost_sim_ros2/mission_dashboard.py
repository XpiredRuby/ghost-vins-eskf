"""Headless recruiter-facing web dashboard for the complete GHOST mission."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import threading
from typing import Any
from urllib.parse import urlparse

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GHOST Mission Control</title>
<style>
:root{color-scheme:dark;--bg:#090d16;--panel:#111827;--line:#273449;--text:#e7eefb;--muted:#93a4bd;--cyan:#31d6ff;--yellow:#ffd166;--green:#51e39a;--magenta:#ff68d4;--red:#ff5d6c}
*{box-sizing:border-box} body{margin:0;background:radial-gradient(circle at top,#17213a 0,#090d16 55%);font:14px/1.35 Inter,system-ui,sans-serif;color:var(--text)}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--line);background:#0b1120dd;position:sticky;top:0;z-index:2} h1{font-size:18px;margin:0;letter-spacing:.08em} .sub{color:var(--muted);font-size:12px}.badge{padding:6px 10px;border-radius:999px;background:#1d2940;font-weight:700}.visible{color:var(--green)}.hidden{color:var(--red)}
main{display:grid;grid-template-columns:minmax(560px,1fr) 340px;gap:14px;padding:14px;max-width:1500px;margin:auto}.panel{background:#101827e8;border:1px solid var(--line);border-radius:14px;box-shadow:0 18px 45px #0006;overflow:hidden}.canvas-wrap{position:relative;min-height:650px}canvas{display:block;width:100%;height:650px;background:#080d16}.legend{position:absolute;left:14px;bottom:12px;display:flex;gap:12px;flex-wrap:wrap;background:#080d16d9;padding:8px 10px;border-radius:10px;font-size:12px}.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px}.side{display:flex;flex-direction:column;gap:12px}.card{padding:13px 14px}.card h2{font-size:12px;letter-spacing:.1em;color:var(--muted);margin:0 0 10px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.metric{background:#0b1220;border:1px solid #202c40;border-radius:9px;padding:9px}.metric b{display:block;font-size:16px;margin-top:3px}.wide{grid-column:1/-1}.status{font-weight:800;font-size:15px}.bar{height:7px;background:#202c40;border-radius:9px;overflow:hidden;margin-top:7px}.bar>span{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--magenta))}.small{font-size:12px;color:var(--muted)}pre{white-space:pre-wrap;font:11px/1.45 ui-monospace,monospace;color:#aebdd4;margin:0;max-height:150px;overflow:auto}@media(max-width:980px){main{grid-template-columns:1fr}.canvas-wrap,canvas{min-height:520px;height:520px}}
</style>
</head>
<body>
<header><div><h1>GHOST MISSION CONTROL</h1><div class="sub">GPS-denied occlusion-aware target tracking • software mission demo</div></div><div id="visibilityBadge" class="badge">CONNECTING</div></header>
<main>
<section class="panel canvas-wrap"><canvas id="world"></canvas><div class="legend">
<span><i class="dot" style="background:#31d6ff"></i>Target truth</span><span><i class="dot" style="background:#ffd166"></i>Observer</span><span><i class="dot" style="background:#51e39a"></i>IMM</span><span><i class="dot" style="background:#ff68d4"></i>GHOST-MH</span><span><i class="dot" style="background:#ff5d6c"></i>Occluded LOS</span></div></section>
<aside class="side">
<section class="panel card"><h2>MISSION</h2><div class="grid">
<div class="metric"><span class="small">Elapsed</span><b id="elapsed">—</b></div><div class="metric"><span class="small">State</span><b id="missionState">—</b></div>
<div class="metric wide"><span class="small">Visibility</span><b id="visibility">—</b></div>
<div class="metric"><span class="small">Separation</span><b id="range">—</b></div><div class="metric"><span class="small">Nav mode</span><b id="navMode">—</b></div>
</div></section>
<section class="panel card"><h2>TRACKING & OCCLUSION</h2><div class="grid">
<div class="metric"><span class="small">Obstacle losses</span><b id="occlusions">0</b></div><div class="metric"><span class="small">Reacquisitions</span><b id="reacq">0</b></div>
<div class="metric"><span class="small">IMM hidden outputs</span><b id="immHidden">0</b></div><div class="metric"><span class="small">MH hidden outputs</span><b id="mhHidden">0</b></div>
<div class="metric wide"><span class="small">Longest measured obstacle loss</span><b id="longest">0.00 s</b></div>
</div></section>
<section class="panel card"><h2>ACCEPTANCE</h2><div id="verdict" class="status">RUNNING</div><div class="bar"><span id="progress" style="width:0%"></span></div><div id="acceptance" class="small" style="margin-top:9px">Waiting for evaluator…</div></section>
<section class="panel card"><h2>CLAIM BOUNDARY</h2><div class="small">Local-frame software simulation. Camera measurements are suppressed by range, field of view, and obstacle line-of-sight. This demonstrates estimation, prediction, guidance, and reacquisition—not GPS-denied self-localization or real flight certification.</div></section>
<section class="panel card"><h2>LIVE STATUS</h2><pre id="raw">Waiting for ROS topics…</pre></section>
</aside></main>
<script>
const canvas=document.getElementById('world'),ctx=canvas.getContext('2d');let state={};
function resize(){const r=canvas.getBoundingClientRect();const d=devicePixelRatio||1;canvas.width=Math.floor(r.width*d);canvas.height=Math.floor(r.height*d);ctx.setTransform(d,0,0,d,0,0)}addEventListener('resize',resize);resize();
function val(o,p,d=null){try{return p.split('.').reduce((a,k)=>a[k],o)??d}catch{return d}}
function fmt(n,d=2){return Number.isFinite(+n)?(+n).toFixed(d):'—'}
function render(){const W=canvas.clientWidth,H=canvas.clientHeight;ctx.clearRect(0,0,W,H);const bounds=val(state,'world.bounds',[-6,6,-4,4]);const [xmin,xmax,ymin,ymax]=bounds;const pad=38,s=Math.min((W-2*pad)/(xmax-xmin),(H-2*pad)/(ymax-ymin));const ox=(W-s*(xmax-xmin))/2,oy=(H+s*(ymax-ymin))/2;const P=p=>[ox+(p[0]-xmin)*s,oy-(p[1]-ymin)*s];
ctx.strokeStyle='#26354c';ctx.lineWidth=1;for(let x=Math.ceil(xmin);x<=xmax;x++){const a=P([x,ymin]),b=P([x,ymax]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke()}for(let y=Math.ceil(ymin);y<=ymax;y++){const a=P([xmin,y]),b=P([xmax,y]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke()}
ctx.strokeStyle='#66758e';ctx.lineWidth=2;const tl=P([xmin,ymax]);ctx.strokeRect(tl[0],tl[1],(xmax-xmin)*s,(ymax-ymin)*s);
for(const o of val(state,'world.obstacles',[])){const a=P([o.xmin,o.ymax]);ctx.fillStyle='#343d4f';ctx.strokeStyle='#657087';ctx.lineWidth=2;ctx.fillRect(a[0],a[1],(o.xmax-o.xmin)*s,(o.ymax-o.ymin)*s);ctx.strokeRect(a[0],a[1],(o.xmax-o.xmin)*s,(o.ymax-o.ymin)*s);ctx.fillStyle='#aeb9ca';ctx.font='12px system-ui';ctx.fillText(o.name,a[0]+5,a[1]+16)}
function trail(points,color,width=2){if(!points||points.length<2)return;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>{const q=P(p);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.stroke()}trail(state.target_trail,'#177b98',2);trail(state.observer_trail,'#9e7720',2);
const obs=val(state,'observer.position'),target=val(state,'target.position'),yaw=val(state,'observer.yaw',0),visible=val(state,'visibility.visible',false);if(obs){const c=P(obs),range=val(state,'world.camera_range_m',8)*s,fov=val(state,'world.camera_fov_deg',118)*Math.PI/180;ctx.fillStyle=visible?'#1e9f7230':'#ff5d6c22';ctx.strokeStyle=visible?'#51e39a88':'#ff5d6c88';ctx.beginPath();ctx.moveTo(...c);ctx.arc(c[0],c[1],range,-yaw-fov/2,-yaw+fov/2);ctx.closePath();ctx.fill();ctx.stroke()}
if(obs&&target){const a=P(obs),b=P(target);ctx.strokeStyle=visible?'#51e39a':'#ff5d6c';ctx.setLineDash([7,6]);ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();ctx.setLineDash([])}
const navPath=val(state,'nav.planned_path_m',[]);trail(navPath,'#ff68d4',3);const goal=val(state,'nav.navigation_goal_m');if(goal){const p=P(goal);ctx.strokeStyle='#ff68d4';ctx.lineWidth=2;ctx.strokeRect(p[0]-6,p[1]-6,12,12)}
function future(payload,color){const hs=payload&&payload.hypotheses||[];hs.slice(0,4).forEach((h,i)=>trail((h.path||[]).map(q=>[q.x_m,q.y_m]),color,Math.max(1,3-i*.5)))}future(state.imm_futures,'#51e39a99');future(state.mh_futures,'#ff68d499');
function circle(p,color,r=7){if(!p)return;const q=P(p);ctx.fillStyle=color;ctx.beginPath();ctx.arc(q[0],q[1],r,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#fff9';ctx.lineWidth=1;ctx.stroke()}circle(target,'#31d6ff',8);circle(val(state,'imm.position'),'#51e39a',6);circle(val(state,'mh.position'),'#ff68d4',6);
if(obs){const q=P(obs);ctx.save();ctx.translate(q[0],q[1]);ctx.rotate(-yaw);ctx.fillStyle='#ffd166';ctx.beginPath();ctx.moveTo(12,0);ctx.lineTo(-9,-7);ctx.lineTo(-6,0);ctx.lineTo(-9,7);ctx.closePath();ctx.fill();ctx.restore()}
const mission=state.mission||{},ev=state.evaluation||{},nav=state.nav||{},vis=state.visibility||{};document.getElementById('elapsed').textContent=fmt(mission.elapsed_s,1)+' s';document.getElementById('missionState').textContent=mission.mission_complete?'COMPLETE':'ACTIVE';document.getElementById('visibility').textContent=vis.visible?'VISIBLE':(vis.visibility_reason||'HIDDEN');document.getElementById('range').textContent=fmt(vis.range_m,2)+' m';document.getElementById('navMode').textContent=(nav.mode||'WAITING').replaceAll('_',' ');document.getElementById('occlusions').textContent=ev.obstacle_occlusion_count||0;document.getElementById('reacq').textContent=ev.reacquisition_count||0;document.getElementById('immHidden').textContent=ev.imm_outputs_during_obstacle_occlusion||0;document.getElementById('mhHidden').textContent=ev.mh_outputs_during_obstacle_occlusion||0;document.getElementById('longest').textContent=fmt(ev.longest_obstacle_occlusion_s,2)+' s';
const badge=document.getElementById('visibilityBadge');badge.textContent=vis.visible?'VISIBLE':'HIDDEN';badge.className='badge '+(vis.visible?'visible':'hidden');const acc=ev.acceptance||{};const keys=Object.keys(acc),done=keys.filter(k=>acc[k]).length,pct=keys.length?100*done/keys.length:0;document.getElementById('progress').style.width=pct+'%';document.getElementById('verdict').textContent=ev.passed?'PASS':(mission.mission_complete?'REVIEW':'RUNNING');document.getElementById('acceptance').textContent=keys.map(k=>(acc[k]?'✓ ':'○ ')+k.replaceAll('_',' ')).join(' · ');document.getElementById('raw').textContent=JSON.stringify({visibility:vis.visibility_reason,nav:nav.mode,tracker:nav.tracker_source,collision_count:mission.collision_count,out_of_bounds_count:mission.out_of_bounds_count},null,2)}
async function poll(){try{const r=await fetch('/api/state',{cache:'no-store'});state=await r.json();render()}catch(e){document.getElementById('visibilityBadge').textContent='DISCONNECTED'}setTimeout(poll,100)}poll();
</script></body></html>"""


class DashboardState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: dict[str, Any] = {
            "world": {},
            "mission": {},
            "visibility": {},
            "nav": {},
            "evaluation": {},
            "target": {},
            "observer": {},
            "imm": {},
            "mh": {},
            "imm_futures": {},
            "mh_futures": {},
            "measurement": {},
            "target_trail": [],
            "observer_trail": [],
        }

    def update(self, key: str, value: Any) -> None:
        with self.lock:
            self.data[key] = value

    def update_pose(self, key: str, position: list[float], yaw: float | None = None) -> None:
        with self.lock:
            payload = {"position": position}
            if yaw is not None:
                payload["yaw"] = yaw
            self.data[key] = payload
            trail_key = f"{key}_trail"
            if trail_key in self.data:
                trail = self.data[trail_key]
                if not trail or math.hypot(trail[-1][0] - position[0], trail[-1][1] - position[1]) > 0.025:
                    trail.append(position)
                if len(trail) > 700:
                    del trail[: len(trail) - 700]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.data))


class MissionDashboard(Node):
    def __init__(self) -> None:
        super().__init__("ghost_mission_dashboard")
        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 8088)
        self.host = str(self.get_parameter("host").value)
        self.port = int(self.get_parameter("port").value)
        self.state = DashboardState()
        qos = QoSProfile(depth=20)
        transient_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(String, "/ghost/sim/world_json", lambda m: self.on_json("world", m), transient_qos)
        self.create_subscription(String, "/ghost/sim/mission_status_json", lambda m: self.on_json("mission", m), qos)
        self.create_subscription(String, "/ghost/sim/visibility_json", lambda m: self.on_json("visibility", m), qos)
        self.create_subscription(String, "/ghost/nav/status_json", lambda m: self.on_json("nav", m), qos)
        self.create_subscription(String, "/ghost/evaluation/status_json", lambda m: self.on_json("evaluation", m), qos)
        self.create_subscription(String, "/ghost/tracker_imm/futures_json", lambda m: self.on_json("imm_futures", m), qos)
        self.create_subscription(String, "/ghost/tracker_mh/futures_json", lambda m: self.on_json("mh_futures", m), qos)
        self.create_subscription(PoseWithCovarianceStamped, "/ghost/sim/target_truth", self.on_target, qos)
        self.create_subscription(PoseWithCovarianceStamped, "/ghost/vision/target_pose", self.on_measurement, qos)
        self.create_subscription(Odometry, "/ghost/sim/observer_odom", self.on_observer, qos)
        self.create_subscription(Odometry, "/ghost/tracker_imm/target_odom", lambda m: self.on_tracker("imm", m), qos)
        self.create_subscription(Odometry, "/ghost/tracker_mh/target_odom", lambda m: self.on_tracker("mh", m), qos)
        self.server = ThreadingHTTPServer((self.host, self.port), self.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, name="ghost-dashboard", daemon=True)
        self.thread.start()
        self.get_logger().info(f"GHOST mission dashboard: http://{self.host}:{self.port}")

    def on_json(self, key: str, msg: String) -> None:
        try:
            self.state.update(key, json.loads(msg.data))
        except json.JSONDecodeError:
            return

    def on_target(self, msg: PoseWithCovarianceStamped) -> None:
        self.state.update_pose("target", [float(msg.pose.pose.position.x), float(msg.pose.pose.position.y)])

    def on_measurement(self, msg: PoseWithCovarianceStamped) -> None:
        self.state.update("measurement", {"position": [float(msg.pose.pose.position.x), float(msg.pose.pose.position.y)]})

    def on_observer(self, msg: Odometry) -> None:
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.state.update_pose("observer", [float(msg.pose.pose.position.x), float(msg.pose.pose.position.y)], yaw)

    def on_tracker(self, key: str, msg: Odometry) -> None:
        self.state.update(key, {"position": [float(msg.pose.pose.position.x), float(msg.pose.pose.position.y)], "velocity": [float(msg.twist.twist.linear.x), float(msg.twist.twist.linear.y)]})

    def handler(self):
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path == "/":
                    self.send_payload(HTTPStatus.OK, "text/html; charset=utf-8", HTML.encode("utf-8"))
                elif path == "/api/state":
                    payload = (json.dumps(state.snapshot(), separators=(",", ":")) + "\n").encode("utf-8")
                    self.send_payload(HTTPStatus.OK, "application/json; charset=utf-8", payload)
                elif path == "/api/health":
                    self.send_payload(HTTPStatus.OK, "application/json; charset=utf-8", b'{"status":"ok"}\n')
                else:
                    self.send_payload(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", b'{"error":"not found"}\n')

            def send_payload(self, status: HTTPStatus, content_type: str, payload: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        return Handler

    def destroy_node(self) -> bool:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = MissionDashboard()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
