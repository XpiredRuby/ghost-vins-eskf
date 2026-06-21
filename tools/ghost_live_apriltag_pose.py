import math
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response
from pupil_apriltags import Detector

DEVICE = "/dev/video0"
WIDTH = 640
HEIGHT = 480
FPS = 30
PORT = 8081

# Temporary camera model until checkerboard calibration is done.
# The eMeet C960 is roughly wide-angle. This is good enough for bearing/range bring-up,
# not final validation.
FX = 650.0
FY = 650.0
CX = WIDTH / 2.0
CY = HEIGHT / 2.0

# Use 0.10 m only when the physical printed tag is actually 10 cm wide.
# A phone-displayed tag is fine for detection, but range will be approximate.
TAG_SIZE_M = 0.10

CAMERA_MATRIX = np.array(
    [[FX, 0.0, CX], [0.0, FY, CY], [0.0, 0.0, 1.0]], dtype=np.float64
)
DIST_COEFFS = np.zeros((4, 1), dtype=np.float64)

TAG_OBJECT_POINTS = np.array(
    [
        [-TAG_SIZE_M / 2, -TAG_SIZE_M / 2, 0.0],
        [TAG_SIZE_M / 2, -TAG_SIZE_M / 2, 0.0],
        [TAG_SIZE_M / 2, TAG_SIZE_M / 2, 0.0],
        [-TAG_SIZE_M / 2, TAG_SIZE_M / 2, 0.0],
    ],
    dtype=np.float64,
)

app = Flask(__name__)

lock = threading.Lock()
latest_jpeg = None
stats = {
    "fps": 0.0,
    "tags": 0,
    "last_id": None,
    "range_m": None,
    "bearing_deg": None,
}


def estimate_pose(tag):
    image_points = tag.corners.astype(np.float64)
    ok, rvec, tvec = cv2.solvePnP(
        TAG_OBJECT_POINTS,
        image_points,
        CAMERA_MATRIX,
        DIST_COEFFS,
        flags=cv2.SOLVEPNP_IPPE_SQUARE,
    )
    if not ok:
        return None

    x = float(tvec[0][0])
    y = float(tvec[1][0])
    z = float(tvec[2][0])
    range_m = math.sqrt(x * x + y * y + z * z)
    bearing_deg = math.degrees(math.atan2(x, z))
    return rvec, tvec, range_m, bearing_deg


def draw_axis(frame, rvec, tvec):
    axis_len = TAG_SIZE_M * 0.65
    axis_points = np.array(
        [[0, 0, 0], [axis_len, 0, 0], [0, axis_len, 0], [0, 0, -axis_len]],
        dtype=np.float64,
    )
    projected, _ = cv2.projectPoints(axis_points, rvec, tvec, CAMERA_MATRIX, DIST_COEFFS)
    projected = projected.reshape(-1, 2).astype(int)
    origin = tuple(projected[0])
    cv2.line(frame, origin, tuple(projected[1]), (0, 0, 255), 2)
    cv2.line(frame, origin, tuple(projected[2]), (0, 255, 0), 2)
    cv2.line(frame, origin, tuple(projected[3]), (255, 0, 0), 2)


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
        range_m = None
        bearing_deg = None

        for tag in tags:
            corners = tag.corners.astype(int)
            for i in range(4):
                p1 = tuple(corners[i])
                p2 = tuple(corners[(i + 1) % 4])
                cv2.line(frame, p1, p2, (0, 255, 0), 2)

            center = tuple(tag.center.astype(int))
            last_id = int(tag.tag_id)
            cv2.circle(frame, center, 5, (0, 0, 255), -1)

            pose = estimate_pose(tag)
            if pose is not None:
                rvec, tvec, range_m, bearing_deg = pose
                draw_axis(frame, rvec, tvec)
                text = f"id={tag.tag_id} range={range_m:.2f}m bearing={bearing_deg:.1f}deg"
            else:
                text = f"id={tag.tag_id} pose=FAILED"

            cv2.putText(
                frame,
                text,
                (center[0] + 8, center[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (0, 255, 0),
                2,
            )

        count += 1
        now = time.time()
        if now - t0 >= 1.0:
            stats["fps"] = count / (now - t0)
            stats["tags"] = len(tags)
            stats["last_id"] = last_id
            stats["range_m"] = range_m
            stats["bearing_deg"] = bearing_deg
            count = 0
            t0 = now

        range_txt = "NA" if range_m is None else f"{range_m:.2f}m"
        bearing_txt = "NA" if bearing_deg is None else f"{bearing_deg:.1f}deg"
        overlay = (
            f"FPS {stats['fps']:.1f} | Tags {len(tags)} | ID {last_id} | "
            f"Range {range_txt} | Bearing {bearing_txt}"
        )
        cv2.rectangle(frame, (0, 0), (WIDTH, 34), (0, 0, 0), -1)
        cv2.putText(
            frame,
            overlay,
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
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
<title>GHOST USB AprilTag Pose Live</title>
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
<div class="badge">GHOST USB AprilTag Pose Live /dev/video0</div>
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
    print("Note: range is approximate until camera calibration + printed 10 cm tag.")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
