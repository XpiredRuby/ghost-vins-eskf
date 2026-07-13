from __future__ import annotations

import tarfile
from pathlib import Path

from analysis.ghost_x_release import (
    build_traceability,
    collect_phase_status,
    create_reproducible_tar,
    requirement_status,
    sha256_file,
)


def test_requirement_status_preserves_physical_gates() -> None:
    status, _ = requirement_status("VNV-003", "G4")
    assert status == "PHYSICAL_CAMPAIGN_PENDING"
    status, _ = requirement_status("EST-006", "G5")
    assert status == "SOFTWARE_VERIFIED"
    status, _ = requirement_status("RT-001", "G9")
    assert status == "QUALIFIED_SOFTWARE_OR_BENCH_EVIDENCE"


def test_traceability_has_all_requirements() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    rows = build_traceability(repo_root)
    assert len(rows) >= 30
    assert len({row["requirement_id"] for row in rows}) == len(rows)
    assert all(not row["missing_tests"] for row in rows)


def test_phase_status_covers_g0_through_g11() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    phases = collect_phase_status(repo_root)
    assert [row["phase"] for row in phases] == [f"G{index}" for index in range(12)]
    assert any("PHYSICAL_EXECUTION_PENDING" in row["software_status"] for row in phases)


def test_reproducible_archive(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    (root / "b.txt").write_text("beta\n", encoding="utf-8")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    create_reproducible_tar(root, first, ["b.txt", "a.txt"])
    create_reproducible_tar(root, second, ["a.txt", "b.txt"])
    assert sha256_file(first) == sha256_file(second)
    with tarfile.open(first, "r:gz") as archive:
        assert archive.getnames() == ["a.txt", "b.txt"]
