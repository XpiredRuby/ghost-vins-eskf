import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from capture_usb_hardware_inventory import capture_inventory, sanitize_text  # noqa: E402


def test_sanitize_text_redacts_sensitive_lines_mac_and_ip():
    text = "model=USB Cam\nID_SERIAL=SECRET123\nmac address=aa:bb:cc:dd:ee:ff\nhost=192.168.1.20\n"
    clean = sanitize_text(text)
    assert "SECRET123" not in clean
    assert "aa:bb:cc:dd:ee:ff" not in clean
    assert "192.168.1.20" not in clean
    assert "model=USB Cam" in clean


def test_capture_inventory_separates_private_and_public_outputs(tmp_path: Path):
    calibration = tmp_path / "camera_calibration.json"
    calibration.write_text('{"rms":0.5}', encoding="utf-8")

    def runner(command):
        return 0, "USB Camera model\nID_SERIAL=SECRET\nIP 10.0.0.5\n", ""

    out = tmp_path / "inventory"
    summary = capture_inventory("/dev/video9", out, calibration=calibration, runner=runner)
    private = out / "private_raw_do_not_publish"
    public = out / "public_review_before_publish"

    assert summary["camera_backend"] == "USB_UVC_WEBCAM"
    assert len(summary["commands"]) == 7
    assert "SECRET" in (private / "udev_camera.txt").read_text()
    assert "SECRET" not in (public / "udev_camera.txt").read_text()
    public_summary = json.loads((public / "hardware_inventory_public.json").read_text())
    assert public_summary["private_directory"] == "REDACTED"
    assert public_summary["calibration"]["filename"] == calibration.name
    assert public_summary["calibration"]["path_redacted"] is True
