import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Calibrate GHOST USB camera from checkerboard images")
    parser.add_argument("--images", default=str(Path.home() / "ghost_calib_images"))
    parser.add_argument("--out", default=str(Path.home() / "ghost_camera_calibration.json"))
    parser.add_argument("--cols", type=int, default=9, help="checkerboard inner corners across")
    parser.add_argument("--rows", type=int, default=6, help="checkerboard inner corners down")
    parser.add_argument("--square-size", type=float, default=0.024, help="checkerboard square size in meters")
    parser.add_argument("--show-rejects", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    image_dir = Path(args.images)
    image_paths = sorted(list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.png")))
    if not image_paths:
        raise SystemExit(f"No calibration images found in {image_dir}")

    pattern = (args.cols, args.rows)
    objp = np.zeros((args.rows * args.cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0 : args.cols, 0 : args.rows].T.reshape(-1, 2)
    objp *= args.square_size

    object_points = []
    image_points = []
    accepted = []
    rejected = []
    image_size = None

    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    )

    for path in image_paths:
        img = cv2.imread(str(path))
        if img is None:
            rejected.append((path.name, "read_failed"))
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        image_size = gray.shape[::-1]
        ok, corners = cv2.findChessboardCorners(gray, pattern, None)
        if not ok:
            rejected.append((path.name, "corners_not_found"))
            continue

        corners_refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        object_points.append(objp)
        image_points.append(corners_refined)
        accepted.append(path.name)

    if len(accepted) < 10:
        raise SystemExit(
            f"Only {len(accepted)} usable images. Need at least 10, preferably 20-30. "
            f"Rejected: {rejected[:10]}"
        )

    rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points, image_points, image_size, None, None
    )

    per_view_errors = []
    for i, obj in enumerate(object_points):
        projected, _ = cv2.projectPoints(obj, rvecs[i], tvecs[i], camera_matrix, dist_coeffs)
        err = cv2.norm(image_points[i], projected, cv2.NORM_L2) / len(projected)
        per_view_errors.append(float(err))

    result = {
        "model": "pinhole",
        "image_width": int(image_size[0]),
        "image_height": int(image_size[1]),
        "checkerboard_inner_corners": {"cols": args.cols, "rows": args.rows},
        "square_size_m": args.square_size,
        "rms_reprojection_error_px": float(rms),
        "mean_per_view_error_px": float(np.mean(per_view_errors)),
        "max_per_view_error_px": float(np.max(per_view_errors)),
        "camera_matrix": camera_matrix.tolist(),
        "dist_coeffs": dist_coeffs.reshape(-1).tolist(),
        "accepted_images": accepted,
        "rejected_images": [{"file": name, "reason": reason} for name, reason in rejected],
    }

    out = Path(args.out)
    out.write_text(json.dumps(result, indent=2))

    print(f"Accepted images: {len(accepted)}")
    print(f"Rejected images: {len(rejected)}")
    print(f"RMS reprojection error: {rms:.4f} px")
    print(f"Mean per-view error: {np.mean(per_view_errors):.4f} px")
    print(f"Max per-view error: {np.max(per_view_errors):.4f} px")
    print(f"Saved: {out}")

    if rms < 0.5:
        print("Calibration quality: strong")
    elif rms < 0.8:
        print("Calibration quality: MVP pass")
    else:
        print("Calibration quality: FAIL - collect sharper/more varied images")

    if args.show_rejects and rejected:
        print("Rejected:")
        for name, reason in rejected:
            print(f"  {name}: {reason}")


if __name__ == "__main__":
    main()
