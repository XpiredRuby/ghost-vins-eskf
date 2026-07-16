from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
INDEX = DOCS / "index.html"
SUMMARY = DOCS / "GHOST_PUBLIC_RESULTS_SUMMARY.json"


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "img" and values.get("src"):
            self.images.append(str(values["src"]))
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))


def load(name: str) -> dict:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_public_results_summary_matches_primary_evidence() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    hardware = load("GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json")
    status = load("GHOST_X_SOFTWARE_STATUS.json")
    g8 = load("GHOST_X_G8_FAULT_REPORT.json")
    g10 = load("GHOST_X_G10_CI_REPORT.json")

    dropout = hardware["accepted_results"]["short_dropout_reacquisition"]
    assert summary["hardware"]["measured_occlusion_s"] == dropout["measured_occlusion_duration_s"]
    assert summary["hardware"]["ghost_top1_error_m"] == dropout["ghost_top1_error_m"]
    assert summary["hardware"]["constant_velocity_error_m"] == dropout["constant_velocity_error_m"]
    assert summary["hardware"]["absolute_accuracy_validated"] is False
    assert summary["faults"]["passed_faults"] == g8["passed_faults"] == 12
    assert summary["verification"]["ci_passed"] == g10["summary"]["passed_count"] == 47
    assert summary["verification"]["requirements_traceable"] == status["requirements"]["traceable"] == 34
    assert summary["release_scope_complete"] is True


def test_public_results_assets_exist_and_are_nontrivial() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assets = [path for group in summary["assets"].values() for path in group]
    assert len(assets) == 18
    for relative in assets:
        path = DOCS / relative
        assert path.is_file(), relative
        assert path.stat().st_size > 20_000, relative
        if path.suffix == ".svg":
            assert "<svg" in path.read_text(encoding="utf-8")[:1000]


def test_landing_page_uses_generated_results_and_claim_boundaries() -> None:
    html = INDEX.read_text(encoding="utf-8")
    parser = AssetParser()
    parser.feed(html)

    assert len(parser.images) >= 9
    for source in parser.images:
        assert (DOCS / source).is_file(), source

    required_phrases = [
        "2.451 s",
        "12 / 12",
        "34 / 34",
        "47 / 47",
        "absolute position accuracy",
        "hard-real-time",
        "Original floor-grid capture",
        "Last-seen hold beat GHOST-MH",
    ]
    for phrase in required_phrases:
        assert phrase in html

    stale_or_unsafe = [
        "Physical covariance, grid accuracy and paired hardware results remain pending",
        "GHOST-MH statistically outperforms formal IMM",
        "validated real-world tracking accuracy",
    ]
    for phrase in stale_or_unsafe:
        assert phrase not in html


def test_landing_page_local_evidence_links_resolve() -> None:
    parser = AssetParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    for href in parser.links:
        if href.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = href.split("#", 1)[0]
        assert target
        assert (DOCS / target).exists(), href


def test_summary_csv_has_expected_engineering_rows() -> None:
    text = (DOCS / "GHOST_PUBLIC_RESULTS_TABLE.csv").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.strip()]
    assert len(rows) >= 9
    assert re.search(r"Hardware,Measured occlusion,2\.450970", text)
    assert "Verification,Requirements traceable,34,of 34" in text


def test_markdown_results_report_embeds_generated_plots() -> None:
    report = (DOCS / "GHOST_PUBLIC_RESULTS_REPORT.md").read_text(encoding="utf-8")
    images = re.findall(r"!\[[^\]]*\]\((assets/results/[^)]+)\)", report)
    assert len(images) >= 9
    for relative in images:
        assert (DOCS / relative).is_file(), relative
    assert "24/24" in report
    assert "12/12" in report
    assert "does **not** claim hard-real-time" in report
