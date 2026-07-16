# GHOST-X Final Research Package

Release: `ghost-x-software-v1`

## Read this first

GHOST-X software is complete and reproducible. The formal operator-assisted physical measurement and controlled-truth campaigns remain pending, so physical accuracy and flight-qualification claims are prohibited.

## Core reports

- [Software verification](GHOST_X_SOFTWARE_VERIFICATION_REPORT.md)
- [Requirements traceability](GHOST_X_FINAL_TRACEABILITY.csv)
- [Approved and prohibited claims](GHOST_X_APPROVED_CLAIMS.md)
- [Failure gallery](GHOST_X_FAILURE_GALLERY.md)
- [No-purchase audit](GHOST_X_NO_PURCHASE_AUDIT.md)
- [90-second demo](GHOST_X_90_SECOND_DEMO.md)
- [10-minute technical defense](GHOST_X_TECHNICAL_DEFENSE.md)

## Phase evidence

### G0 — SOFTWARE_COMPLETE

- [GHOST_X_G0_BASELINE.md](GHOST_X_G0_BASELINE.md)
- [GHOST_X_BASELINE_MANIFEST.json](GHOST_X_BASELINE_MANIFEST.json)

### G1 — SOFTWARE_COMPLETE

- [GHOST_X_G1_REQUIREMENTS_AND_VNV.md](GHOST_X_G1_REQUIREMENTS_AND_VNV.md)
- [GHOST_X_G1_VALIDATION.json](GHOST_X_G1_VALIDATION.json)

### G2 — SOFTWARE_COMPLETE

- [GHOST_X_G2_DATA_CONTRACTS.md](GHOST_X_G2_DATA_CONTRACTS.md)
- [GHOST_X_G2_VALIDATION.json](GHOST_X_G2_VALIDATION.json)
- [GHOST_X_G2_RUNTIME_VALIDATION.json](GHOST_X_G2_RUNTIME_VALIDATION.json)

### G3 — SOFTWARE_COMPLETE_PHYSICAL_EXECUTION_PENDING

- [GHOST_X_G3_MEASUREMENT_PROTOCOL.md](GHOST_X_G3_MEASUREMENT_PROTOCOL.md)
- [GHOST_X_G3_READINESS.json](GHOST_X_G3_READINESS.json)

### G4 — SOFTWARE_COMPLETE_PHYSICAL_EXECUTION_PENDING

- [GHOST_X_G4_CONTROLLED_TRUTH.md](GHOST_X_G4_CONTROLLED_TRUTH.md)
- [GHOST_X_G4_VALIDATION.json](GHOST_X_G4_VALIDATION.json)

### G5 — SOFTWARE_COMPLETE

- [GHOST_X_G5_CPP_LIBRARY.md](GHOST_X_G5_CPP_LIBRARY.md)
- [GHOST_X_G5_EQUIVALENCE.json](GHOST_X_G5_EQUIVALENCE.json)
- [GHOST_X_G5_VALIDATION.json](GHOST_X_G5_VALIDATION.json)

### G6 — SOFTWARE_COMPLETE

- [GHOST_X_G6_CONSISTENCY.md](GHOST_X_G6_CONSISTENCY.md)
- [GHOST_X_G6_CONSISTENCY.json](GHOST_X_G6_CONSISTENCY.json)

### G7 — SOFTWARE_COMPLETE

- [GHOST_X_G7_TRADE_STUDY.md](GHOST_X_G7_TRADE_STUDY.md)
- [GHOST_X_G7_TRADE_STUDY.json](GHOST_X_G7_TRADE_STUDY.json)

### G8 — SOFTWARE_COMPLETE

- [GHOST_X_G8_FAULT_REPORT.md](GHOST_X_G8_FAULT_REPORT.md)
- [GHOST_X_G8_FAULT_REPORT.json](GHOST_X_G8_FAULT_REPORT.json)

### G9 — SOFTWARE_COMPLETE

- [GHOST_X_G9_RUNTIME_REPORT.md](GHOST_X_G9_RUNTIME_REPORT.md)
- [GHOST_X_G9_RUNTIME_REPORT.json](GHOST_X_G9_RUNTIME_REPORT.json)

### G10 — SOFTWARE_COMPLETE

- [GHOST_X_G10_CI_REPORT.md](GHOST_X_G10_CI_REPORT.md)
- [GHOST_X_G10_CI_REPORT.json](GHOST_X_G10_CI_REPORT.json)
- [ghost-x-regression.yml](../../.github/workflows/ghost-x-regression.yml)

### G11 — SOFTWARE_COMPLETE

- [GHOST_X_G11_FIXED_LAG.md](GHOST_X_G11_FIXED_LAG.md)
- [GHOST_X_G11_FIXED_LAG.json](GHOST_X_G11_FIXED_LAG.json)

### G12 — SOFTWARE_COMPLETE

- [build_ghost_x_release.py](../../ghost_sim_ros2/tools/build_ghost_x_release.py)
- [GHOST_X_FINAL_RESEARCH_PACKAGE.md](GHOST_X_FINAL_RESEARCH_PACKAGE.md)
- [GHOST_X_APPROVED_CLAIMS.md](GHOST_X_APPROVED_CLAIMS.md)
- [GHOST_X_FAILURE_GALLERY.md](GHOST_X_FAILURE_GALLERY.md)

## Reproduction

```bash
python3 ghost_sim_ros2/tools/run_ghost_x_g10_ci.py \
  --acceptance ghost_sim_ros2/config/ghost_x_g10_acceptance.yaml \
  --repo-root "$PWD" \
  --cpp-build-dir /tmp/ghost_x_cpp_build \
  --out-dir /tmp/ghost_x_g10
```

The GitHub workflow `.github/workflows/ghost-x-regression.yml` runs the same software gates and uploads the complete G10 report.
