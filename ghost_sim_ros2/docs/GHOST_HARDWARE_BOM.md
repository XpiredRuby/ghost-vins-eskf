# GHOST Hardware, Interfaces and Bill of Materials

## Configuration status

```text
Camera backend: USB_UVC_WEBCAM
BOM status: TEMPLATE_PENDING_PHYSICAL_INVENTORY_AND_PHOTOS
Claims boundary: EXACT_LABELS_COSTS_AND_PHOTOS_REQUIRE_PHYSICAL_VERIFICATION
```

GHOST uses a **standard USB UVC webcam connected to the Raspberry Pi over USB**. The USB camera is accessed through Linux V4L2/UVC and is not a CSI camera. The project value is in calibrated pose estimation, formal IMM tracking, bounded dropout handling, validation and evidence—not in presenting a consumer webcam as specialized flight hardware.

The machine-readable source for this page is [`hardware_bom.json`](hardware_bom.json).

## Reproducible system boundary

```text
printed AprilTag target
        |
        v optical image
USB UVC webcam
        |
        v USB + V4L2/UVC
Raspberry Pi / ROS 2 Jazzy
        |
        +--> AprilTag pose publisher
        +--> formal IMM tracker
        +--> heuristic GHOST-MH tracker
        +--> trial recorder and operator services
        |
        v JSONL / JSON / CSV / static HTML
analysis, validation and public replay
```

## Bill of materials

Exact model, label and cost fields intentionally remain pending until the physical hardware is available. This prevents a polished BOM from becoming an unverified inventory claim.

| ID | Component | Quantity | Interface | Role | Current verification status |
|---|---|---:|---|---|---|
| `compute` | Raspberry Pi | 1 | USB, Ethernet/Wi-Fi | Edge compute, ROS 2, trackers and recording | Exact model/RAM/revision pending OS query or label photo |
| `vision_sensor` | Standard USB UVC webcam | 1 | USB, V4L2/UVC | Calibrated AprilTag imagery | Vendor/product ID, model, modes and lens pending `lsusb`/V4L2/label verification |
| `fiducial` | AprilTag 36h11 tag 0 | 1 | Optical | Known target geometry | Family/ID documented; printed size must be remeasured |
| `camera_mount` | Rigid USB webcam mount | 1 | Mechanical | Fixed camera geometry | Mount type/material/attachment pending photo |
| `tag_carrier` | Rigid tag backing/carrier | 1 | Mechanical | Prevents tag flex | Material, attachment and dimensions pending photo |
| `power_supply` | Raspberry Pi power supply | 1 | Model-specific power input | Regulated Pi and USB camera power | Voltage/current/model pending label photo |
| `usb_cable` | USB webcam cable | 1 | USB | Video data and camera power | Connector type and length pending photo |
| `network` | Local Ethernet or Wi-Fi | 1 | SSH/HTTP | Operation and evidence transfer | Connection method recorded per session |
| `occluder` | Opaque occluder | 1 | Optical | Controlled measurement gaps | Material, dimensions and position pending photo |
| `metrology` | Tape/ruler and marked path/grid | 1 set | Physical ground truth | Standoff, grid and endpoint definition | Required for the next validation session |

## Interface control table

| From | To | Interface | Data/power | Purpose |
|---|---|---|---|---|
| USB UVC webcam | Raspberry Pi | USB + V4L2/UVC | Frames and camera power | Image acquisition |
| AprilTag publisher | Formal IMM / GHOST-MH | ROS 2 DDS, `/ghost/vision/target_pose` | Timestamped pose and covariance metadata | Shared estimator input |
| Raspberry Pi | Operator computer | SSH + HTTP over local network | Commands, status and replay | Remote operation without altering measurements |
| Trial recorder | Analysis/public replay | JSONL, JSON, CSV and static HTML | Evidence artifacts | Reproducibility and audit |

## USB-camera engineering record

The physical inventory session must capture:

```text
lsusb
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --all
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Record at minimum:

- USB vendor and product ID;
- manufacturer and model when safely available;
- device node used by the validated setup;
- active pixel format, resolution and frame rate;
- supported exposure, white-balance and focus controls;
- whether autofocus or autoexposure can be disabled;
- calibration-file identity and reprojection error;
- observed frame rate, dropped-frame behavior and arrival-time jitter;
- USB connector/cable type and approximate length.

USB webcam timestamps in this project are software/arrival timestamps unless hardware timestamp support is independently verified. Do not describe them as shutter-open timestamps.

## Cost summary

| Cost category | Current value |
|---|---:|
| Core functional hardware | Pending receipts or owner estimate |
| Mounting and consumables | Pending |
| Optional development hardware | Pending |
| Total reproducible build cost | Pending |

Already-owned hardware should still receive an approximate replacement cost, but the table must distinguish replacement cost from money spent specifically for GHOST.

## Required photo package

Save photographs under:

```text
ghost_sim_ros2/docs/assets/hardware_bom/
```

Use these filenames:

| File | Required content |
|---|---|
| `01_complete_setup_front.jpg` | Full USB webcam, Pi, target, occluder and marked path from the front |
| `02_complete_setup_side.jpg` | Side view showing camera-to-tag geometry and mount rigidity |
| `03_raspberry_pi_closeup.jpg` | Pi enclosure and connections; no serial numbers or network credentials |
| `04_usb_webcam_closeup.jpg` | USB webcam and mount; preserve model label only when safe |
| `05_apriltag_carrier.jpg` | Tag 0, measured physical size and rigid backing |
| `06_power_and_cable_routing.jpg` | Power supply, USB routing and strain relief |
| `07_standoff_measurement.jpg` | Measured camera-to-tag standoff and coordinate origin |
| `08_ground_truth_grid.jpg` | Measured non-collinear points and axes |
| `09_occluder_and_motion_path.jpg` | Occluder, start, turn and endpoint marks |
| `10_hero_hardware_setup.jpg` | Clean portfolio photograph without private information |

## Photo callout convention

The final annotated overview should use numbered callouts:

```text
[1] USB UVC webcam
[2] rigid camera mount
[3] Raspberry Pi
[4] USB data cable
[5] regulated power supply
[6] AprilTag 36h11 tag 0
[7] rigid target carrier
[8] opaque occluder
[9] measured path/grid
[10] coordinate origin
```

Every label should name the component and its engineering function, not merely identify what it looks like.

## Hardware limitations

- Consumer USB webcam with rolling-shutter and software-arrival timing unless proven otherwise.
- AprilTag-dependent measurement front end rather than general object perception.
- Indoor controlled-lighting validation configuration.
- Fixed-camera geometry for the current covariance and grid protocols.
- No environmental enclosure, shock qualification or flight-qualified components.
- No independent hardware time synchronization.
- No physical vehicle guidance or flight-control claim.
- Exact operating envelope remains pending measured angle, range, lighting and speed trials.

## Selection rationale

The USB UVC webcam remains the correct baseline because it is supported by the working V4L2 pipeline and allows engineering effort to focus on estimation, dropout handling, validation and GNC integration. A global-shutter USB camera may reduce motion distortion later, but changing the sensor before the present setup is fully validated would add an uncontrolled variable.

## Inventory completion gate

The BOM may be marked `PHYSICALLY_VERIFIED` only after:

1. exact Pi and webcam identity are recorded;
2. active camera modes and controls are captured;
3. tag size is physically measured;
4. power ratings and cable interfaces are recorded;
5. cost fields are completed or explicitly marked already-owned;
6. all required photos are captured and privacy-reviewed;
7. the setup photo matches the hardware used for the associated validation session;
8. `hardware_bom.json` is updated and reviewed.

Until then, this page is a reproducibility template and interface record—not a claim that every manufacturer/model field has already been verified.
