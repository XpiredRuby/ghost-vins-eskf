from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
DOCS = PACKAGE_ROOT / "docs"
INDEX = DOCS / "index.html"
CSS = DOCS / "assets" / "showcase.css"
JS = DOCS / "assets" / "showcase.js"
SHOWCASE = DOCS / "data" / "GHOST_INTERACTIVE_SHOWCASE_DATA.json"
REPLAY = DOCS / "data" / "GHOST_HARDWARE_REPLAY_20260716.json"
CHECKLIST = DOCS / "GHOST_INTERACTIVE_EVIDENCE_CHECKLIST.md"
GENERATOR = PACKAGE_ROOT / "tools" / "generate_interactive_showcase_data.py"

RAW_TRIAL = Path(
    "/home/xpired/ghost_trials/physical_validation_20260711T183400Z/"
    "browser_guided_runs/20260716T014453Z/recorder_trials/20260715_194502"
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag == "script" and values.get("src"):
            self.scripts.append(str(values["src"]))
        if tag == "img" and values.get("src"):
            self.images.append(str(values["src"]))


def load(name: str) -> dict:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_map(report: dict) -> dict[str, object]:
    return {str(row["id"]): row["actual"] for row in report["summary"]["checks"]}


def test_generated_showcase_matches_primary_evidence_exactly() -> None:
    showcase = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    hardware = load("GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json")
    g4 = load("GHOST_X_G4_VALIDATION.json")
    g8 = load("GHOST_X_G8_FAULT_REPORT.json")
    g9 = load("GHOST_X_G9_RUNTIME_REPORT.json")
    g10 = load("GHOST_X_G10_CI_REPORT.json")
    checks = check_map(g10)

    hero = {row["id"]: row for row in showcase["hero_metrics"]}
    dropout = hardware["accepted_results"]["short_dropout_reacquisition"]
    assert hero["hardware_dropout"]["value"] == dropout["measured_occlusion_duration_s"]
    assert hero["hardware_dropout"]["sample_basis"] == "N=1 intended hardware dropout"
    assert hero["controlled_trials"]["value"] == g4["campaign"]["accepted_trials"] == 24
    assert hero["fault_cases"]["value"] == g8["passed_faults"] == 12
    assert hero["rt002"]["value"] == g9["requirements"]["RT-002"]["publication_rate_hz"]
    assert hero["rt002"]["threshold"] == g9["requirements"]["RT-002"]["limits"]["minimum_rate_hz"]
    assert hero["rt002"]["status"] == "NOT_MET"

    estimators = {row["id"]: row for row in showcase["estimator_comparison"]["estimators"]}
    assert estimators["cv_kalman"]["overall_rmse_m"] == checks["G4_CV_KALMAN_POSITION_RMSE"]
    assert estimators["cv_kalman"]["hidden_rmse_m"] == checks["G4_CV_KALMAN_HIDDEN_RMSE"]
    assert estimators["formal_imm"]["overall_rmse_m"] == checks["G4_FORMAL_IMM_POSITION_RMSE"]
    assert estimators["formal_imm"]["hidden_rmse_m"] == checks["G4_FORMAL_IMM_HIDDEN_RMSE"]
    assert estimators["ghost_mh"]["overall_rmse_m"] == checks["G4_GHOST_MH_POSITION_RMSE"]
    assert estimators["ghost_mh"]["hidden_rmse_m"] == checks["G4_GHOST_MH_HIDDEN_RMSE"]

    for estimator in estimators.values():
        assert estimator["reacquisition_time_s"] is None
        assert estimator["reset_count"] is None
        assert "No symmetric retained" in estimator["reacquisition_time_unavailable_reason"]
        assert "No symmetric retained" in estimator["reset_count_unavailable_reason"]


def test_runtime_failures_are_exact_and_prominent_in_data() -> None:
    showcase = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    runtime = showcase["runtime"]
    rt1 = runtime["requirements"]["RT-001"]
    rt2 = runtime["requirements"]["RT-002"]
    rt3 = runtime["requirements"]["RT-003"]

    assert rt1["passed"] is False
    assert rt1["p95_ms"] == 233.1105807500001
    assert rt1["limits_ms"]["p95"] == 150.0
    assert rt1["p99_ms"] == 365.87323451999987
    assert rt1["limits_ms"]["p99"] == 250.0
    assert rt1["sample_count"] == 354

    assert rt2["passed"] is False
    assert rt2["publication_rate_hz"] == 3.4433068896378227
    assert rt2["limits"]["minimum_rate_hz"] == 29.7
    assert rt2["deadline_miss_fraction"] == 0.5
    assert rt2["limits"]["maximum_deadline_miss_fraction"] == 0.01
    assert rt2["interarrival_ms"]["count"] == 18

    assert rt3["passed"] is True
    assert rt3["thermal_sample_count"] == 141
    assert rt3["throttling_clear"] is True
    assert runtime["requirements_all_passed"] is False
    assert runtime["real_time_claim_status"] == "HARD_REAL_TIME_NOT_CLAIMED_REQUIREMENTS_NOT_MET"
    assert any("RT-001" in line for line in runtime["what_did_not_pass"])
    assert any("RT-002" in line for line in runtime["what_did_not_pass"])


def test_fault_campaign_is_complete_and_symmetric() -> None:
    showcase = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    faults = showcase["fault_testing"]
    assert faults["fault_count"] == faults["passed_faults"] == 12
    assert faults["failed_faults"] == 0
    assert len(faults["faults"]) == 12
    expected = {
        "camera_disconnect",
        "frozen_measurement",
        "duplicate_measurement",
        "false_detection",
        "covariance_corruption",
        "latency",
        "out_of_sequence_data",
        "node_restart",
        "cpu_saturation",
        "network_degradation",
        "parameter_mismatch",
        "lighting_degradation",
    }
    assert {row["fault"] for row in faults["faults"]} == expected
    for row in faults["faults"]:
        assert row["passed"] is True
        assert row["detected"] is True
        assert row["isolated"] is True
        assert row["recovery_ok"] is True
        assert set(row["position_error_rmse_m"]) == {"cv_kalman", "formal_imm", "ghost_mh"}


def test_replay_contains_recorded_samples_only_and_reviewed_window() -> None:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    summary = load("guided_hardware_evidence/20260716_guided_sequence_summary.json")

    assert replay["data_class"] == "MEASURED_HARDWARE"
    assert replay["video_available"] is False
    assert replay["sequence_start_wall_time_s"] == summary["sequence_start_wall_time_s"]
    assert replay["sequence_end_wall_time_s"] == summary["sequence_end_wall_time_s"]
    assert replay["cue_window_start_t_s"] == 1.0
    assert replay["cue_window_end_t_s"] == 1.0 + summary["sequence_duration_s"]
    assert len(replay["measurements"]) == summary["vision_sample_count"] == 767
    assert len(replay["events"]) == 14
    assert len(replay["status_changes"]) > 0
    assert len(replay["imm_estimates"]) > 300
    assert len(replay["mh_estimates"]) > 300
    assert "No smoothing" in replay["measurement_note"]
    assert "not interpolated" in replay["tracker_note"]
    assert "No approved camera frames" in replay["video_note"]

    for key in ("measurements", "imm_estimates", "mh_estimates", "events", "status_changes"):
        timestamps = [float(row["t_s"]) for row in replay[key]]
        assert timestamps == sorted(timestamps)
        assert min(timestamps) >= 0.0
        assert max(timestamps) <= replay["duration_s"]

    for key in ("vision_pose", "events", "status", "imm_futures", "mh_futures"):
        source = replay["provenance"][key]
        assert not source["logical_name"].startswith("/")
        assert re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
        assert source["size_bytes"] > 0


def test_replay_hashes_match_external_sources_when_available() -> None:
    if not RAW_TRIAL.is_dir():
        return
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    mapping = {
        "vision_pose": "vision_pose.jsonl",
        "events": "events.jsonl",
        "status": "status.jsonl",
        "imm_futures": "imm_futures.jsonl",
        "mh_futures": "mh_futures.jsonl",
    }
    for key, filename in mapping.items():
        path = RAW_TRIAL / filename
        assert path.stat().st_size == replay["provenance"][key]["size_bytes"]
        assert sha256(path) == replay["provenance"][key]["sha256"]


def test_page_has_required_interactive_sections_and_controls() -> None:
    html = INDEX.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(html)

    required_ids = {
        "mission",
        "architecture",
        "stage-rail",
        "replay",
        "replay-play",
        "replay-scrubber",
        "replay-speed",
        "replay-xy-chart",
        "replay-time-chart",
        "comparison",
        "estimator-rmse-chart",
        "estimator-runtime-chart",
        "occlusion",
        "scenario-selector",
        "scenario-chart",
        "hardware",
        "faults",
        "fault-filter",
        "fault-sort",
        "fault-recovery-chart",
        "runtime",
        "runtime-deadline-chart",
        "limitations",
        "evidence",
        "download-grid",
    }
    assert required_ids <= parser.ids

    order = [
        html.index('id="mission"'),
        html.index('id="architecture"'),
        html.index('id="replay"'),
        html.index('id="comparison"'),
        html.index('id="occlusion"'),
        html.index('id="hardware"'),
        html.index('id="faults"'),
        html.index('id="runtime"'),
        html.index('id="limitations"'),
        html.index('id="evidence"'),
    ]
    assert order == sorted(order)
    assert "Autonomous Object Tracking for Follower-Drone Applications" in html
    assert "No physical drone was flown" in html
    assert "implemented, not physically evidenced" in html
    assert "The timing requirements did not all pass" in html
    assert "Limitations &amp; Claim Boundaries" in html
    assert "No retained camera footage" in html
    assert "No smoothing, interpolation, or synthetic filler" in html
    assert any(src.endswith("plotly-2.35.2.min.js") for src in parser.scripts)
    assert "assets/showcase.js" in parser.scripts


def test_page_does_not_use_unsafe_claims() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (INDEX, JS, CHECKLIST)
    ).lower()
    forbidden = [
        "physical autonomous flight validated",
        "flight-proven",
        "flight ready",
        "flight-ready",
        "production ready",
        "production-ready",
        "metrology-grade accuracy validated",
        "hard-real-time certified",
        "ghost-mh is universally superior",
        "state-of-the-art",
    ]
    for phrase in forbidden:
        assert phrase not in combined

    assert "no physical closed-loop drone flight" in combined
    assert "no independent metrology-grade ground truth" in combined
    assert "no universal" in combined
    assert "rt-001" in combined
    assert "rt-002" in combined


def test_interaction_code_uses_sample_hold_not_interpolation() -> None:
    script = JS.read_text(encoding="utf-8")
    assert "latestAtOrBefore" in script
    assert "latest actual sample at or before" in script
    assert "interpolate(" not in script
    assert "No smoothing" in script
    assert "Not retained symmetrically" in script
    assert "Plotly.react" in script
    assert "requestAnimationFrame" in script


def test_local_assets_and_links_resolve() -> None:
    parser = PageParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    assert CSS.is_file() and CSS.stat().st_size > 20_000
    assert JS.is_file() and JS.stat().st_size > 20_000
    assert GENERATOR.is_file() and GENERATOR.stat().st_size > 20_000
    assert SHOWCASE.is_file() and SHOWCASE.stat().st_size > 20_000
    assert REPLAY.is_file() and REPLAY.stat().st_size > 100_000
    assert CHECKLIST.is_file() and CHECKLIST.stat().st_size > 2_000

    for target in parser.links + parser.images + parser.scripts:
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#", 1)[0].split("?", 1)[0]
        assert clean, target
        assert (DOCS / clean).exists(), target


def test_source_type_badges_and_sample_boundaries_are_explicit() -> None:
    showcase = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    assert {row["badge"] for row in showcase["hero_metrics"]} >= {
        "MEASURED_HARDWARE",
        "SYNTHETIC_SOFTWARE",
    }
    scenarios = showcase["occlusion_scenarios"]
    assert scenarios["short_hide"]["sample_basis"] == "N=1 intended hardware dropout"
    assert "N=2 simulated obstacle occlusions" in scenarios["long_hide"]["sample_basis"]
    assert "correlated video samples" in scenarios["lateral_motion"]["sample_basis"]
    assert "32 correlated pose samples" in scenarios["range_change"]["sample_basis"]
    assert "89 correlated pose samples" in scenarios["range_change"]["sample_basis"]
    assert scenarios["short_hide"]["metrics"]["hidden_drift_m"] is None
    assert scenarios["long_hide"]["metrics"]["first_frame_errors_m"] is None


def test_evidence_checklist_lists_unavailable_evidence() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    required = [
        "Symmetric reacquisition time",
        "Symmetric reset count",
        "Metrology-grade physical target truth",
        "Physical closed-loop drone-flight results",
        "Physical ICM-42688-P identity/rate/data validation",
        "Approved camera footage",
        "Outdoor or adversarial visual-target hardware results",
        "Hard-real-time certification",
    ]
    for phrase in required:
        assert phrase in text


def test_fault_metrics_are_labeled_as_shared_stream_outputs() -> None:
    data = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    fault = data["fault_testing"]
    assert fault["fault_count"] == 12
    assert fault["passed_faults"] == 12
    assert fault["source_stream"] == "canonical_streams/g4_repeated_reentry_rep01.jsonl"
    assert fault["unique_recovery_time_count"] == 2
    assert sorted(group["count"] for group in fault["recovery_time_groups"]) == [5, 7]
    assert fault["unique_rmse_profile_count"] == 6
    assert sorted(group["count"] for group in fault["rmse_profile_groups"]) == [1, 1, 1, 1, 2, 6]
    assert "shared canonical" in fault["metric_interpretation"].lower()
    assert "detected" in fault["pass_definition"].lower()
    assert "isolated" in fault["pass_definition"].lower()


def test_runtime_interpretation_separates_reporting_from_requirement_pass() -> None:
    data = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    runtime = data["runtime"]
    assert runtime["deadline_rows_total"] == 12
    assert runtime["deadline_rows_met"] == 11
    assert runtime["deadline_rows_not_met"] == 1
    miss = runtime["deadline_miss_rows"][0]
    assert miss["implementation"] == "cpp_production"
    assert miss["estimator"] == "cv"
    assert miss["stress_workers"] == 0
    assert runtime["rt002_root_cause_status"] == "NOT_ESTABLISHED"
    assert "does not mean the timing requirement passed" in runtime["reporting_check_interpretation"]
    assert data["hardware"]["max_process_rss_mb"] == 69.8203125
    assert data["hardware"]["max_estimator_benchmark_rss_mb"] == 70.33984375


def test_interpretation_notes_are_visible_on_page() -> None:
    html = INDEX.read_text(encoding="utf-8")
    script = JS.read_text(encoding="utf-8")
    for element_id in (
        "fault-pass-definition",
        "fault-metric-boundary",
        "fault-group-summary",
        "rt002-interpretation",
        "deadline-anomaly-interpretation",
        "reporting-check-interpretation",
        "deadline-row-summary",
    ):
        assert f'id="{element_id}"' in html
        assert f'#{element_id}' in script
