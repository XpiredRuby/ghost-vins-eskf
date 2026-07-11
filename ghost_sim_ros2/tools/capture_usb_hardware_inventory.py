"""Capture private raw and publication-safe USB/V4L2 hardware inventory evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SENSITIVE_LINE = re.compile(
    r"(?i)(serial(number)?|mac[ _-]?address|ip[ _-]?address|ssid|password|credential|wifi.*key|unique id)"
)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")

COMMANDS = {
    "uname.txt": ["uname", "-a"],
    "usb_devices.txt": ["lsusb"],
    "v4l2_devices.txt": ["v4l2-ctl", "--list-devices"],
    "camera_all.txt": ["v4l2-ctl", "-d", "{device}", "--all"],
    "camera_controls.txt": ["v4l2-ctl", "-d", "{device}", "--list-ctrls-menus"],
    "camera_formats.txt": ["v4l2-ctl", "-d", "{device}", "--list-formats-ext"],
    "udev_camera.txt": ["udevadm", "info", "--query=property", "--name", "{device}"],
}


def capture_inventory(
    device: str,
    out_dir: Path,
    *,
    calibration: Path | None = None,
    runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    out = out_dir.expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"inventory directory must not already contain files: {out}")
    out.mkdir(parents=True, exist_ok=True)
    private_dir = out / "private_raw_do_not_publish"
    public_dir = out / "public_review_before_publish"
    private_dir.mkdir()
    public_dir.mkdir()
    runner = runner or run_command
    command_results = []

    for filename, template in COMMANDS.items():
        command = [part.format(device=device) for part in template]
        returncode, stdout, stderr = runner(command)
        raw = f"$ {' '.join(command)}\nreturncode={returncode}\n\nSTDOUT\n{stdout}\nSTDERR\n{stderr}\n"
        (private_dir / filename).write_text(raw, encoding="utf-8")
        sanitized = sanitize_text(raw)
        (public_dir / filename).write_text(sanitized, encoding="utf-8")
        command_results.append(
            {
                "filename": filename,
                "command": command,
                "returncode": returncode,
                "public_sha256": sha256(public_dir / filename),
                "raw_private_sha256": sha256(private_dir / filename),
            }
        )

    pi_model = read_text_if_exists(Path("/proc/device-tree/model"))
    if pi_model:
        (private_dir / "pi_model.txt").write_text(pi_model + "\n", encoding="utf-8")
        (public_dir / "pi_model.txt").write_text(sanitize_text(pi_model) + "\n", encoding="utf-8")

    calibration_summary = None
    if calibration is not None:
        path = calibration.expanduser()
        if not path.is_file():
            raise ValueError(f"calibration file does not exist: {path}")
        calibration_summary = {
            "filename": path.name,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "path_redacted": True,
        }

    summary = {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "camera_backend": "USB_UVC_WEBCAM",
        "device_node": device,
        "pi_model": pi_model,
        "calibration": calibration_summary,
        "commands": command_results,
        "publication_status": "REQUIRES_HUMAN_PRIVACY_REVIEW_BEFORE_COPYING_PUBLIC_FILES_TO_REPOSITORY",
        "private_directory": str(private_dir),
        "public_directory": str(public_dir),
        "manual_fields_pending": [
            "webcam manufacturer/model label",
            "Raspberry Pi RAM/revision confirmation",
            "power-supply voltage/current label",
            "USB connector type and cable length",
            "mount material and attachment",
            "component replacement costs",
        ],
    }
    (out / "inventory_summary_private_paths.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    public_summary = dict(summary)
    public_summary["private_directory"] = "REDACTED"
    public_summary["public_directory"] = "REDACTED"
    (public_dir / "hardware_inventory_public.json").write_text(
        json.dumps(public_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (public_dir / "PRIVACY_REVIEW_REQUIRED.md").write_text(
        "# Privacy Review Required\n\n"
        "Inspect every public file before publication. Remove serial numbers, MAC/IP addresses, "
        "Wi-Fi details, unique IDs, private paths and unrelated personal information. The automatic "
        "redactor is a defense-in-depth aid, not a guarantee.\n",
        encoding="utf-8",
    )
    return summary


def sanitize_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        udev_property = re.match(r"(?i)^((?:ID_PATH|ID_SERIAL)[^=]*)=(.*)$", line)
        if udev_property:
            lines.append(f"{udev_property.group(1)}=[REDACTED]")
            continue
        if SENSITIVE_LINE.search(line):
            lines.append("[REDACTED SENSITIVE LINE]")
            continue
        line = MAC.sub("[REDACTED_MAC]", line)
        line = IPV4.sub("[REDACTED_IP]", line)
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def run_command(command: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def read_text_if_exists(path: Path) -> str | None:
    try:
        return path.read_bytes().replace(b"\x00", b"").decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a privacy-separated USB UVC hardware inventory.")
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--calibration", type=Path)
    args = parser.parse_args(argv)
    summary = capture_inventory(args.device, args.out_dir, calibration=args.calibration)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
