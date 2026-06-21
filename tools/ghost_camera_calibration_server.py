import argparse
import json
import threading
import time
from pathlib import Path

import cv2
from flask import Flask, Response, redirect


def parse_args():
    parser = argparse.ArgumentParser(description="GHOST USB camera calibration capture server")
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--out", default=str(Path.home() / "ghost_calib_images"))
    return parser.parse_args()


args = parse_args()
app = Flask(__name__)
out_dir = Path(args.out)
out_dir.mkdir(parents=True, exist_ok=True)

lock = threading.Lock()
latest_frame = None
latest_jpeg = None
capture_count = 0
stats = {"fps": 0.0}


def camera_loop():
    global latest_frame, latest_jpeg

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open {args.device}")

    count = 0
    t0 = time.time()

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        display = frame.copy()
        cv2.rectangle(display, (0, 0), (args.width, 34), (0, 0, 0), -1)
        cv2.putText(
            display,
            f"GHOST calibration capture | FPS {stats['fps']:.1f} | images {capture_count}",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )

        ok, jpg = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            with lock:
                latest_frame = frame
                latest_jpeg = jpg.tobytes()

        count += 1
        now = time.time()
        if now - t0 >= 1.0:
            stats["fps"] = count / (now - t0)
            count = 0
            t0 = now


def mjpeg_stream():
    while True:
        with lock:
            frame = latest_jpeg
        if frame is None:
            time.sleep(0.01)
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Cache-Control: no-store\r\n\r\n" + frame + b"\r\n"
        )


@app.route("/")
def index():
    return """
<!doctype html>
<html>
<head>
<title>GHOST Camera Calibration</title>
<style>
html, body { margin:0; width:100%; height:100%; background:#050505; color:white; font-family:Arial,sans-serif; }
.wrap { display:flex; flex-direction:column; height:100vh; }
.bar { padding:10px; background:#111; display:flex; gap:10px; align-items:center; }
button, a { font-size:16px; padding:8px 12px; border-radius:6px; border:0; background:#1f7aec; color:white; text-decoration:none; }
.hint { color:#ccc; font-size:14px; }
img { flex:1; object-fit:contain; min-height:0; background:#050505; }
</style>
</head>
<body>
<div class="wrap">
  <div class="bar">
    <a href="/capture">Capture image</a>
    <a href="/state">State</a>
    <span class="hint">Move checkerboard around. Capture 20-30 sharp views: center, corners, tilted, near/far.</span>
  </div>
  <img src="/stream">
</div>
</body>
</html>
"""


@app.route("/stream")
def stream():
    return Response(mjpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/capture")
def capture():
    global capture_count
    with lock:
        frame = None if latest_frame is None else latest_frame.copy()
    if frame is None:
        return "No frame yet", 503

    capture_count += 1
    path = out_dir / f"calib_{capture_count:03d}.jpg"
    cv2.imwrite(str(path), frame)
    return redirect("/")


@app.route("/state")
def state():
    return Response(
        json.dumps(
            {
                "device": args.device,
                "resolution": [args.width, args.height],
                "fps": stats["fps"],
                "capture_count": capture_count,
                "out_dir": str(out_dir),
            },
            indent=2,
        ),
        mimetype="application/json",
    )


if __name__ == "__main__":
    thread = threading.Thread(target=camera_loop, daemon=True)
    thread.start()
    print(f"Open: http://192.168.1.142:{args.port}")
    print(f"Saving calibration images to: {out_dir}")
    print("Press Ctrl+C to stop")
    app.run(host="0.0.0.0", port=args.port, threaded=True)
