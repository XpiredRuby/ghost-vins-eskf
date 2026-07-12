import argparse
import json
import math
import time
from pathlib import Path



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', default='/dev/video0')
    ap.add_argument('--duration-s', type=float, default=90.0)
    ap.add_argument('--tag-size', type=float, default=0.1)
    ap.add_argument('--calib', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    args = ap.parse_args()

    import cv2
    import numpy as np
    from pupil_apriltags import Detector

    args.out_dir.mkdir(parents=True, exist_ok=True)

    calib = json.loads(args.calib.read_text())
    camera_matrix = np.array(calib['camera_matrix'], dtype=np.float64)
    dist_coeffs = np.array(calib['dist_coeffs'], dtype=np.float64).reshape(-1, 1)
    s = args.tag_size
    object_points = np.array([
        [-s / 2, s / 2, 0.0],
        [ s / 2, s / 2, 0.0],
        [ s / 2,-s / 2, 0.0],
        [-s / 2,-s / 2, 0.0],
    ], dtype=np.float64)

    cv2.setNumThreads(1)
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise RuntimeError(f'could not open {args.device}')

    detector = Detector(families='tag36h11')
    rows = []
    first_pose_mono = None
    last_pose_rel = None
    frame_count = 0
    read_failures = 0
    detection_failures = 0
    pnp_failures = 0
    brightness = []
    decision_margins = []
    tag_ids = set()
    start_mono = time.monotonic()
    hard_timeout_s = args.duration_s + 30.0

    try:
        while True:
            now = time.monotonic()
            if first_pose_mono is not None and last_pose_rel is not None and last_pose_rel >= args.duration_s:
                break
            if now - start_mono > hard_timeout_s:
                raise RuntimeError('hard timeout before requested valid-pose duration was covered')

            ok, frame = cap.read()
            if not ok or frame is None:
                read_failures += 1
                continue
            frame_count += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness.append(float(np.mean(gray)))
            tags = detector.detect(gray)
            if not tags:
                detection_failures += 1
                continue

            tag = max(tags, key=lambda item: float(getattr(item, 'decision_margin', 0.0)))
            solved, _rvec, tvec = cv2.solvePnP(
                object_points,
                tag.corners.astype(np.float64),
                camera_matrix,
                dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            if not solved:
                pnp_failures += 1
                continue

            pose_mono = time.monotonic()
            if first_pose_mono is None:
                first_pose_mono = pose_mono
            t_rel = pose_mono - first_pose_mono
            last_pose_rel = t_rel
            wall_s = time.time()
            stamp_sec = int(wall_s)
            stamp_nanosec = int(round((wall_s - stamp_sec) * 1e9))
            if stamp_nanosec >= 1_000_000_000:
                stamp_sec += 1
                stamp_nanosec -= 1_000_000_000

            cam_x = float(tvec[0][0])
            cam_z = float(tvec[2][0])
            tag_id = int(tag.tag_id)
            tag_ids.add(tag_id)
            margin = float(getattr(tag, 'decision_margin', math.nan))
            decision_margins.append(margin)
            rows.append({
                'trial_id': args.out_dir.name,
                'source': 'DIRECT_CAMERA_APRILTAG_SOLVEPNP_NO_ROS_TRANSPORT',
                'wall_time_s': wall_s,
                'ros_time_s': None,
                't_rel_s': t_rel,
                'position': {'x_m': cam_z, 'y_m': cam_x, 'z_m': 0.0},
                'stamp': {'sec': stamp_sec, 'nanosec': stamp_nanosec},
                'tag_id': tag_id,
                'decision_margin': margin,
            })
    finally:
        cap.release()

    if len(rows) < 2:
        raise RuntimeError('fewer than two valid pose samples')

    pose_times = [float(row['t_rel_s']) for row in rows]
    gaps = [pose_times[i] - pose_times[i - 1] for i in range(1, len(pose_times))]
    xs = [float(row['position']['x_m']) for row in rows]
    ys = [float(row['position']['y_m']) for row in rows]
    summary = {
        'source': 'DIRECT_CAMERA_APRILTAG_SOLVEPNP_NO_ROS_TRANSPORT',
        'requested_duration_s': args.duration_s,
        'covered_duration_s': pose_times[-1],
        'frames_ok': frame_count,
        'read_failures': read_failures,
        'detection_failures': detection_failures,
        'pnp_failures': pnp_failures,
        'valid_pose_samples': len(rows),
        'valid_pose_rate_hz': (len(rows) - 1) / pose_times[-1],
        'max_pose_gap_s': max(gaps),
        'tag_ids': sorted(tag_ids),
        'x_span_m': max(xs) - min(xs),
        'y_span_m': max(ys) - min(ys),
        'brightness_mean': float(np.mean(brightness)),
        'brightness_min': float(np.min(brightness)),
        'brightness_max': float(np.max(brightness)),
        'decision_margin_mean': float(np.mean(decision_margins)),
        'decision_margin_min': float(np.min(decision_margins)),
    }

    jsonl = args.out_dir / 'vision_pose.jsonl'
    with jsonl.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, separators=(',', ':')) + '\n')
    (args.out_dir / 'direct_capture_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
