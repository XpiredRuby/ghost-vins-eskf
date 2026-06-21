# GHOST USB Camera Tooling

These scripts are the next USB webcam coding layer:

- `ghost_camera_calibration_server.py`
  - browser-based image capture for camera calibration
  - opens at `http://192.168.1.142:8082`
  - saves images to `~/ghost_calib_images`

- `ghost_calibrate_camera.py`
  - computes the camera matrix and distortion from checkerboard images
  - writes `~/ghost_camera_calibration.json`

- `ghost_live_apriltag_pose_calibrated.py`
  - live AprilTag pose viewer
  - loads `~/ghost_camera_calibration.json` if available
  - falls back to an approximate camera model if calibration is missing

## Run Order

On the Pi:

```bash
source ~/ghost_venv/bin/activate
python ~/ghost_camera_calibration_server.py
```

Open:

```text
http://192.168.1.142:8082
```

Capture 20-30 sharp checkerboard images.

Then calibrate:

```bash
python ~/ghost_calibrate_camera.py --cols 9 --rows 6 --square-size 0.024
```

Adjust `--cols`, `--rows`, and `--square-size` to match the actual printed checkerboard:

- `cols` = number of inner corners across
- `rows` = number of inner corners down
- `square-size` = one square edge length in meters

Then run calibrated pose:

```bash
python ~/ghost_live_apriltag_pose_calibrated.py --tag-size 0.10
```

Open:

```text
http://192.168.1.142:8081
```

## Notes

- Phone-displayed AprilTags are acceptable for detection only.
- Range validation needs a printed tag with a known physical edge length.
- The default tag size is `0.10` meters.
- Calibration quality:
  - `< 0.5 px`: strong
  - `< 0.8 px`: MVP pass
  - `>= 0.8 px`: redo calibration
