# GHOST USB Hardware Inventory Capture

## Purpose

Capture exact Raspberry Pi and USB UVC webcam identity, supported V4L2 modes, controls and calibration provenance while separating private raw device data from files that may later be published.

## Why two output trees exist

Some Linux hardware queries can expose:

- serial numbers;
- USB path identifiers;
- MAC or IP addresses;
- host/network information;
- private filesystem paths;
- unique device identifiers.

The inventory tool therefore creates:

```text
hardware_inventory_<timestamp>/
├── inventory_summary_private_paths.json
├── private_raw_do_not_publish/
└── public_review_before_publish/
```

The automatic redactor is defense in depth, not permission to publish blindly. Every file in `public_review_before_publish` still requires manual privacy review.

## Run during the physical inventory session

From the repository root:

```bash
python3 ghost_sim_ros2/tools/capture_usb_hardware_inventory.py \
  --device /dev/video0 \
  --calibration ~/ghost_camera_calibration.json \
  --out-dir ~/ghost_trials/hardware_inventory_$(date -u +%Y%m%d_%H%M%SZ)
```

The destination must be empty. The tool refuses to mix a new inventory into an existing evidence directory.

## Commands captured

The private and redacted trees receive outputs from:

```text
uname -a
lsusb
v4l2-ctl --list-devices
v4l2-ctl -d <device> --all
v4l2-ctl -d <device> --list-ctrls-menus
v4l2-ctl -d <device> --list-formats-ext
udevadm info --query=property --name <device>
```

When available, `/proc/device-tree/model` is also recorded to identify the Raspberry Pi family.

## Calibration record

When `--calibration` is supplied, the public summary records only:

- calibration filename;
- file size;
- SHA-256;
- `path_redacted: true`.

The absolute calibration path is not copied into the publication-facing JSON.

## Automatic redaction

The public copy redacts or suppresses lines containing common forms of:

- serial number;
- MAC address;
- IP address;
- SSID;
- password/credential/Wi-Fi key;
- unique ID;
- `ID_SERIAL`, `ID_SERIAL_SHORT` and `ID_PATH`.

Each raw/private and redacted/public file receives its own SHA-256 in the inventory summary so later edits are detectable.

## Manual completion fields

Software queries cannot reliably finish every BOM field. Record manually:

- webcam manufacturer/model printed on the device;
- Raspberry Pi RAM/revision confirmation;
- power-supply voltage/current label;
- USB connector type and cable length;
- mount material and attachment method;
- component replacement costs;
- photo filenames that show the validated setup.

Never publish a serial number merely because it appears next to a useful model label. Crop or blur the unique identifier while retaining the generic manufacturer/model when safe.

## Publication gate

The public hardware page and `hardware_bom.json` may be marked physically verified only after:

1. the inventory tool completes without an unexplained command failure;
2. the exact USB webcam and Raspberry Pi fields are reconciled against a label or OS query;
3. every candidate public file receives human privacy review;
4. private raw output remains outside the repository;
5. calibration SHA-256 matches the file used for validation;
6. photos are reviewed for network, account, serial and personal information;
7. machine-readable and Markdown BOM records agree.

## Test

```bash
PYTHONPATH=ghost_sim_ros2/tools \
python3 -m pytest -q ghost_sim_ros2/test/test_usb_hardware_inventory.py
```

The focused tests verify that sensitive lines, MAC addresses and IP addresses are removed and that private/public directory contents remain intentionally different.
