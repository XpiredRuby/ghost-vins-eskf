#!/usr/bin/env python3
from __future__ import annotations

import functools
import http.server
import shutil
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DOCS = PACKAGE_ROOT / "docs"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def chrome_binary() -> str:
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("No supported Chrome/Chromium executable was found")


def run_chrome(chrome: str, url: str, user_data: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    command = [
        chrome,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=20000",
        f"--user-data-dir={user_data}",
        *extra,
        url,
    ]
    return subprocess.run(command, text=True, capture_output=True, timeout=90, check=False)


def main() -> int:
    handler = functools.partial(QuietHandler, directory=str(DOCS))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{port}/index.html"
        chrome = chrome_binary()

        with tempfile.TemporaryDirectory(prefix="ghost-showcase-browser-") as temp_dir:
            temp = Path(temp_dir)
            dump = run_chrome(chrome, url, temp / "profile-dump", "--dump-dom")
            if dump.returncode != 0:
                raise RuntimeError(
                    f"Chrome DOM run failed ({dump.returncode})\nSTDOUT:\n{dump.stdout}\nSTDERR:\n{dump.stderr}"
                )
            dom = dump.stdout
            expected_fragments = [
                'data-showcase-ready="true"',
                'data-hero-metrics="4"',
                'data-stage-buttons="5"',
                'data-estimator-cards="3"',
                'data-fault-rows="12"',
                "3.4433068896378227 Hz",
                "No physical closed-loop drone flight",
                "Not retained symmetrically",
                "RT-001",
                "RT-002",
            ]
            for fragment in expected_fragments:
                if fragment not in dom:
                    raise AssertionError(f"Rendered DOM missing: {fragment}")
            if "data-showcase-error=" in dom:
                raise AssertionError("Interactive page reported a showcase initialization error")

            screenshots = [
                ("desktop.png", "1440,1200"),
                ("mobile.png", "390,844"),
            ]
            for filename, window_size in screenshots:
                screenshot = temp / filename
                result = run_chrome(
                    chrome,
                    url,
                    temp / f"profile-{filename}",
                    f"--window-size={window_size}",
                    f"--screenshot={screenshot}",
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"Chrome screenshot failed for {filename} ({result.returncode})\n{result.stderr}"
                    )
                if not screenshot.is_file() or screenshot.stat().st_size < 20_000:
                    raise AssertionError(f"Screenshot is missing or unexpectedly small: {screenshot}")
                print(f"{filename}: {screenshot.stat().st_size} bytes")

        server.shutdown()
    print("Interactive showcase browser smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
