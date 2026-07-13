"""Browser-based local cue conductor for one GHOST hardware campaign trial."""

from __future__ import annotations

import argparse
import csv
import json
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GHOST Trial Conductor</title><style>
:root{--bg:#07111f;--panel:#102036;--text:#f5f9ff;--muted:#a9bbd3;--cyan:#5de2ff;--green:#62e6a7;--orange:#ffb454;--red:#ff657a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif;min-height:100vh;display:grid;grid-template-rows:auto 1fr auto}.top{padding:14px 20px;background:#0b1728;border-bottom:1px solid #29405f;display:flex;justify-content:space-between;gap:16px}.meta{color:var(--muted)}main{display:grid;place-items:center;padding:22px}.stage{width:min(1100px,100%);text-align:center}.cue{font-size:clamp(54px,11vw,150px);font-weight:950;line-height:.92;letter-spacing:-.05em;margin:12px 0}.count{font-size:clamp(70px,16vw,220px);font-variant-numeric:tabular-nums;font-weight:900;color:var(--cyan);line-height:.9}.instruction{font-size:clamp(18px,3vw,32px);color:var(--muted);max-width:900px;margin:18px auto}.progress{height:14px;background:#152b48;border-radius:999px;overflow:hidden}.bar{height:100%;width:0;background:linear-gradient(90deg,var(--cyan),var(--green))}.controls{display:flex;justify-content:center;flex-wrap:wrap;gap:10px;margin-top:22px}button{border:1px solid #395678;background:#172d49;color:var(--text);font-weight:850;border-radius:10px;padding:13px 19px;font-size:16px;cursor:pointer}button.primary{background:#176f83}button.reject{background:#682536}button:disabled{opacity:.4;cursor:not-allowed}.foot{padding:12px 20px;color:var(--muted);font-size:13px;border-top:1px solid #29405f}.phase-occlude .cue,.phase-reveal .cue{color:var(--orange)}.phase-done .cue{color:var(--green)}.phase-turn .cue{color:#c9acff}.phase-reject .cue{color:var(--red)}
.preview-wrap{display:none;margin:0 auto 18px;width:min(900px,100%);background:#050a12;border:1px solid #29405f;border-radius:12px;overflow:hidden}.preview-wrap.active{display:block}.preview-wrap img{display:block;width:100%;max-height:46vh;object-fit:contain;background:#000}.preview-label{padding:7px 10px;color:var(--muted);font-size:13px;text-align:left}.next{margin:14px auto 0;padding:10px 14px;width:min(900px,100%);border:1px solid #395678;border-radius:10px;background:#0b1728;font-size:clamp(17px,2.4vw,25px);font-weight:900;color:var(--orange)}.overview{margin:12px auto 0;width:min(900px,100%);color:var(--muted);font-size:14px;line-height:1.45}
</style></head><body><div class="top"><strong>GHOST LOCAL TRIAL CONDUCTOR</strong><div class="meta" id="meta">Loading plan…</div></div><main><div class="stage" id="stage"><div class="preview-wrap" id="previewWrap"><div class="preview-label">LIVE CALIBRATED CAMERA VIEW — confirm the full AprilTag is visible before starting</div><img id="preview" alt="Live calibrated camera preview"></div><div class="cue" id="cue">READY</div><div class="count" id="count">—</div><div class="instruction" id="instruction">Arm audio, place the tag on the start mark, and start only when the recorder is already running.</div><div class="next" id="nextCue">UP NEXT: loading…</div><div class="overview" id="overview"></div><div class="progress"><div class="bar" id="bar"></div></div><div class="controls"><button id="arm">Arm audio</button><button class="primary" id="start" disabled>Start cues</button><button id="pause" disabled>Pause</button><button class="reject" id="reject">Reject / stop</button><button id="download">Download local log</button></div></div></main><div class="foot">Cue timing assists the operator. The measured vision gap remains the acceptance source of truth. Do not use chat latency for second-level timing.</div><script>
let plan=null,phaseIndex=-1,phaseStart=0,paused=false,pauseStarted=0,totalPaused=0,raf=null,audio=null,events=[];
const cue=document.getElementById('cue'),count=document.getElementById('count'),instruction=document.getElementById('instruction'),bar=document.getElementById('bar'),stage=document.getElementById('stage'),nextCue=document.getElementById('nextCue'),overview=document.getElementById('overview'),previewWrap=document.getElementById('previewWrap'),preview=document.getElementById('preview');
const post=async(type,extra={})=>{const event={type,trial_id:plan?.trial_id??null,sequence:plan?.sequence??null,phase_index:phaseIndex,client_iso:new Date().toISOString(),performance_ms:performance.now(),...extra};events.push(event);try{await fetch('/api/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(event)})}catch(e){console.warn(e)}};
const speak=text=>{if('speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(text))}if(audio){const o=audio.createOscillator(),g=audio.createGain();o.frequency.value=880;g.gain.value=.13;o.connect(g).connect(audio.destination);o.start();o.stop(audio.currentTime+.14)}};
fetch('/api/plan').then(r=>r.json()).then(p=>{plan=p;document.getElementById('meta').textContent=`#${p.sequence} · ${p.trial_id} · ${p.condition_id}`;const phases=Array.isArray(p.phases)?p.phases:[];overview.textContent=phases.length?`SEQUENCE: ${phases.map(x=>x.cue).join(' → ')}`:'';nextCue.textContent=`UP NEXT: ${phases[0]?.cue||'—'}`;if(typeof p.preview_stream_url==='string'&&p.preview_stream_url.trim()){preview.src=p.preview_stream_url.trim();previewWrap.classList.add('active')}post('page_loaded')}).catch(e=>{cue.textContent='PLAN ERROR';instruction.textContent=e.message});
document.getElementById('arm').onclick=async()=>{audio=new(window.AudioContext||window.webkitAudioContext)();await audio.resume();speak('Audio armed');document.getElementById('start').disabled=false;post('audio_armed')};
document.getElementById('start').onclick=()=>{if(!plan)return;document.getElementById('start').disabled=true;document.getElementById('pause').disabled=false;phaseIndex=-1;nextPhase()};
function nextPhase(){phaseIndex++;if(phaseIndex>=plan.phases.length){finish();return}const p=plan.phases[phaseIndex],n=plan.phases[phaseIndex+1];stage.className=`stage phase-${p.phase_type}`;cue.textContent=p.cue;instruction.textContent=p.instruction;nextCue.textContent=`UP NEXT: ${n?.cue||'COMPLETE'}`;phaseStart=performance.now();totalPaused=0;paused=false;speak(p.speak||p.cue);post('phase_started',{cue:p.cue,duration_s:p.duration_s});if(p.duration_s<=0){setTimeout(nextPhase,650);return}tick()}
function tick(){const p=plan.phases[phaseIndex];if(paused){raf=requestAnimationFrame(tick);return}const elapsed=(performance.now()-phaseStart-totalPaused)/1000,remaining=Math.max(0,p.duration_s-elapsed);count.textContent=remaining.toFixed(1);bar.style.width=`${Math.min(100,100*elapsed/p.duration_s)}%`;if(remaining<=0){post('phase_completed',{cue:p.cue,actual_elapsed_s:elapsed});nextPhase()}else raf=requestAnimationFrame(tick)}
document.getElementById('pause').onclick=()=>{paused=!paused;if(paused){pauseStarted=performance.now();document.getElementById('pause').textContent='Resume';post('paused')}else{totalPaused+=performance.now()-pauseStarted;document.getElementById('pause').textContent='Pause';post('resumed')}};
document.getElementById('reject').onclick=()=>{const reason=prompt('Required rejection reason:');if(!reason)return;cancelAnimationFrame(raf);stage.className='stage phase-reject';cue.textContent='REJECTED';count.textContent='STOP';instruction.textContent=reason;post('trial_rejected',{reason});document.getElementById('pause').disabled=true};
document.getElementById('download').onclick=()=>{const blob=new Blob([JSON.stringify({plan,events},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`${plan?.trial_id||'trial'}_conductor_local_log.json`;a.click();URL.revokeObjectURL(a.href)};
function finish(){cancelAnimationFrame(raf);stage.className='stage phase-done';cue.textContent='DONE';count.textContent='✓';instruction.textContent='Keep all evidence. Verify the measured gap and recorder outputs before marking this trial accepted.';nextCue.textContent='UP NEXT: COMPLETE';bar.style.width='100%';post('cue_sequence_completed');document.getElementById('pause').disabled=true;speak('Trial cue sequence complete')}
</script></body></html>'''


class ConductorServer:
    def __init__(self, campaign_dir: Path, sequence: int, host: str, port: int):
        self.campaign_dir = campaign_dir.expanduser().resolve()
        self.plan = load_plan(self.campaign_dir, sequence)
        self.host = host
        self.port = port
        self.event_path = (
            self.campaign_dir
            / "trial_directories"
            / self.plan["trial_id"]
            / "conductor_events.jsonl"
        )
        self._lock = threading.Lock()

    def handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/":
                    self._send(HTTPStatus.OK, "text/html; charset=utf-8", HTML.encode())
                elif path == "/api/plan":
                    self._send_json(HTTPStatus.OK, outer.plan)
                elif path == "/api/health":
                    self._send_json(HTTPStatus.OK, {"status": "ok", "trial_id": outer.plan["trial_id"]})
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def do_POST(self):
                if urlparse(self.path).path != "/api/events":
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid body length"})
                    return
                try:
                    event = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
                    return
                if not isinstance(event, dict):
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "event must be an object"})
                    return
                event["server_received_at_utc"] = utc_now()
                event["server_trial_id"] = outer.plan["trial_id"]
                outer.event_path.parent.mkdir(parents=True, exist_ok=True)
                with outer._lock, outer.event_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event, sort_keys=True) + "\n")
                self._send_json(HTTPStatus.CREATED, {"saved": True})

            def log_message(self, fmt, *args):
                return

            def _send_json(self, status, value):
                self._send(status, "application/json; charset=utf-8", (json.dumps(value) + "\n").encode())

            def _send(self, status, content_type, payload):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

        return Handler

    def serve(self) -> None:
        server = ThreadingHTTPServer((self.host, self.port), self.handler())
        address = f"http://{self.host if self.host != '0.0.0.0' else '127.0.0.1'}:{self.port}/"
        print(f"trial_id={self.plan['trial_id']}")
        print(f"condition={self.plan['condition_id']}")
        print(f"open={address}")
        print(f"events={self.event_path}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


def load_plan(campaign_dir: Path, sequence: int) -> dict[str, Any]:
    if sequence < 1:
        raise ValueError("sequence must be >= 1")
    order_path = campaign_dir / "randomized_trial_order.csv"
    with order_path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    selected = next((row for row in rows if int(row["sequence"]) == sequence), None)
    if selected is None:
        raise ValueError(f"sequence {sequence} is not present in {order_path}")
    plan_path = campaign_dir / "trial_directories" / selected["trial_id"] / "conductor_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("trial_id") != selected["trial_id"]:
        raise ValueError(f"invalid conductor plan: {plan_path}")
    return plan


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve precise local visual/audio cues for one GHOST campaign trial.")
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--print-plan", action="store_true")
    args = parser.parse_args(argv)

    server = ConductorServer(args.campaign_dir, args.sequence, args.host, args.port)
    if args.print_plan:
        print(json.dumps(server.plan, indent=2, sort_keys=True))
        return 0
    server.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
