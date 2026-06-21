import cv2
import time
import threading
from flask import Flask, Response
from pupil_apriltags import Detector

DEVICE = "/dev/video0"
WIDTH = 640
HEIGHT = 480
FPS = 30
PORT = 8081

app = Flask(__name__)

lock = threading.Lock()
latest_jpeg = None
stats = {"fps": 0.0, "tags": 0, "last_id": None}


def camera_loop():
    global latest_jpeg

    cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open {DEVICE}")

    detector = Detector(families="tag36h11")
    count = 0
    t0 = time.time()

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        tags = detector.detect(gray)

        last_id = None
        for tag in tags:
            corners = tag.corners.astype(int)
            for i in range(4):
                p1 = tuple(corners[i])
                p2 = tuple(corners[(i + 1) % 4])
                cv2.line(frame, p1, p2, (0, 255, 0), 2)

            center = tuple(tag.center.astype(int))
            last_id = int(tag.tag_id)
            cv2.circle(frame, center, 5, (0, 0, 255), -1)
            cv2.putText(
                frame,
                f"id={tag.tag_id}",
                (center[0] + 8, center[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
            )

        count += 1
        now = time.time()
        if now - t0 >= 1.0:
            stats["fps"] = count / (now - t0)
            stats["tags"] = len(tags)
            stats["last_id"] = last_id
            count = 0
            t0 = now

        overlay = f"FPS {stats['fps']:.1f} | Tags {len(tags)} | ID {last_id}"
        cv2.rectangle(frame, (0, 0), (WIDTH, 32), (0, 0, 0), -1)
        cv2.putText(
            frame,
            overlay,
            (10, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with lock:
                latest_jpeg = jpg.tobytes()


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
<title>GHOST USB AprilTag Live</title>
<style>
html, body {
  margin: 0;
  width: 100%;
  height: 100%;
  background: #050505;
  overflow: hidden;
  font-family: Arial, sans-serif;
}
img {
  width: 100vw;
  height: 100vh;
  object-fit: contain;
  display: block;
}
.badge {
  position: fixed;
  top: 10px;
  left: 10px;
  color: white;
  background: rgba(0,0,0,.65);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 15px;
}
</style>
</head>
<body>
<img src="/stream">
<div class="badge">GHOST USB AprilTag Live /dev/video0</div>
</body>
</html>
"""


@app.route("/stream")
def stream():
    return Response(mjpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    thread = threading.Thread(target=camera_loop, daemon=True)
    thread.start()
    print(f"Open: http://192.168.1.142:{PORT}")
    print("Press Ctrl+C to stop")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
