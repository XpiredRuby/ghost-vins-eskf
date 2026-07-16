#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import http.server
import re
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DOCS = PACKAGE_ROOT / "docs"
PUBLISHED_FILES = (
    "index.html",
    "assets/showcase.css",
    "assets/showcase.js",
    "data/GHOST_INTERACTIVE_SHOWCASE_DATA.json",
    "data/GHOST_HARDWARE_REPLAY_20260716.json",
)


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


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_live_files(base_url: str, timeout_s: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_mismatches: list[str] = []
    while time.monotonic() < deadline:
        mismatches: list[str] = []
        cache_buster = str(time.time_ns())
        for relative in PUBLISHED_FILES:
            local = (DOCS / relative).read_bytes()
            url = urllib.parse.urljoin(base_url, relative)
            separator = "&" if "?" in url else "?"
            request = urllib.request.Request(
                f"{url}{separator}ghost_live_smoke={cache_buster}",
                headers={"User-Agent": "GHOST-X-live-browser-smoke/1.0"},
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    remote = response.read()
            except Exception as exc:  # pragma: no cover - diagnostic path
                mismatches.append(f"{relative}: fetch failed: {exc}")
                continue
            if remote != local:
                mismatches.append(
                    f"{relative}: live sha256={sha256_bytes(remote)} local sha256={sha256_bytes(local)}"
                )
        if not mismatches:
            print("Live deployed files match the checked-out Pages artifacts byte-for-byte")
            return
        last_mismatches = mismatches
        time.sleep(4)
    raise AssertionError("Live deployment did not converge to the checked-out files:\n" + "\n".join(last_mismatches))


@contextlib.contextmanager
def local_site() -> Iterator[str]:
    handler = functools.partial(QuietHandler, directory=str(DOCS))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}/"
        finally:
            server.shutdown()
            thread.join(timeout=5)


def add_smoke_query(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("smoke", "1"))
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def assert_rendered_dom(dom: str) -> None:
    expected_fragments = [
        'data-showcase-ready="true"',
        'data-hero-metrics="4"',
        'data-stage-buttons="5"',
        'data-estimator-cards="3"',
        'data-fault-rows="12"',
        'data-smoke-complete="true"',
        'data-smoke-scenario="range_change"',
        "3.4433068896378227 Hz",
        "No physical closed-loop drone flight",
        "Not retained symmetrically",
        "shared canonical evaluation stream",
        "6 exact RMSE profiles and 2 exact recovery-time values",
        "Eleven of twelve measured maximum-execution rows",
        "does not mean the timing requirement passed",
        "RT-001",
        "RT-002",
    ]
    for fragment in expected_fragments:
        if fragment not in dom:
            raise AssertionError(f"Rendered DOM missing: {fragment}")
    if "data-showcase-error=" in dom:
        raise AssertionError("Interactive page reported a showcase initialization error")

    stale_placeholders = [
        "Loading verified metrics from published JSON…",
        "Loading measured and synthetic mission evidence…",
        "Loading evidence-backed stage details…",
        "Awaiting recorded replay data",
        "Awaiting timeline events",
    ]
    for placeholder in stale_placeholders:
        if placeholder in dom:
            raise AssertionError(f"Rendered DOM still contains pre-JavaScript placeholder: {placeholder}")

    plot_count = dom.count("js-plotly-plot")
    if plot_count < 7:
        raise AssertionError(f"Expected at least 7 rendered Plotly charts, found {plot_count}")

    scrubber = re.search(r'id="replay-scrubber"[^>]*max="([0-9.]+)"', dom)
    replay_time = re.search(r'data-smoke-replay-time="([0-9.]+)"', dom)
    if not scrubber or not replay_time:
        raise AssertionError("Replay scrubber did not expose rendered max and exercised time")
    maximum = float(scrubber.group(1))
    current = float(replay_time.group(1))
    if maximum < 100 or not (0 < current < maximum):
        raise AssertionError(f"Replay scrubber was not exercised: value={current}, max={maximum}")

    measurement = re.search(r'id="replay-measurement">([^<]+)</dd>', dom)
    if not measurement or "x " not in measurement.group(1) or " m" not in measurement.group(1):
        raise AssertionError("Replay measurement did not populate with a recorded numeric sample")

    smoke_fault = re.search(r'data-smoke-fault-first="([^"]+)"', dom)
    if not smoke_fault or not smoke_fault.group(1).strip():
        raise AssertionError("Fault-table sorting interaction did not produce a first row")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render and validate the GHOST-X interactive showcase")
    parser.add_argument("--base-url", help="Validate an already deployed site instead of starting a local server")
    parser.add_argument("--output-dir", type=Path, help="Retain rendered DOM and screenshots in this directory")
    return parser.parse_args()


def run_validation(base_url: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    url = add_smoke_query(base_url)
    chrome = chrome_binary()

    dump = run_chrome(chrome, url, output_dir / "profile-dump", "--dump-dom")
    if dump.returncode != 0:
        raise RuntimeError(
            f"Chrome DOM run failed ({dump.returncode})\nSTDOUT:\n{dump.stdout}\nSTDERR:\n{dump.stderr}"
        )
    dom = dump.stdout
    (output_dir / "rendered_dom.html").write_text(dom, encoding="utf-8")
    assert_rendered_dom(dom)

    screenshots = [
        ("desktop.png", "1440,1200"),
        ("mobile.png", "390,844"),
    ]
    summary_lines = [f"url={url}"]
    for filename, window_size in screenshots:
        screenshot = output_dir / filename
        result = run_chrome(
            chrome,
            url,
            output_dir / f"profile-{filename}",
            f"--window-size={window_size}",
            f"--screenshot={screenshot}",
        )
        if result.returncode != 0:
            raise RuntimeError(f"Chrome screenshot failed for {filename} ({result.returncode})\n{result.stderr}")
        if not screenshot.is_file() or screenshot.stat().st_size < 20_000:
            raise AssertionError(f"Screenshot is missing or unexpectedly small: {screenshot}")
        summary_lines.append(f"{filename}={screenshot.stat().st_size} bytes")
        print(summary_lines[-1])
    (output_dir / "smoke_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.output_dir:
        output_context = contextlib.nullcontext(args.output_dir.resolve())
    else:
        output_context = tempfile.TemporaryDirectory(prefix="ghost-showcase-browser-")

    with output_context as raw_output:
        output_dir = Path(raw_output)
        if args.base_url:
            base_url = args.base_url.rstrip("/") + "/"
            verify_live_files(base_url)
            run_validation(base_url, output_dir)
        else:
            with local_site() as base_url:
                run_validation(base_url, output_dir)

    print("Interactive showcase browser smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
