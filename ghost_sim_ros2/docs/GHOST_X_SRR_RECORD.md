# GHOST-X System Requirements Review Record

**Review:** Internal System Requirements Review  
**Date:** 2026-07-12 CDT  
**Baseline branch:** `ghost-x`  
**G0 baseline tag:** `ghost-drone-mission-v1`

## Review inputs

- `GHOST_X_MASTER_PLAN.md`
- `GHOST_X_G0_BASELINE.md`
- `GHOST_X_BASELINE_MANIFEST.json`
- `GHOST_X_CLAIM_BOUNDARIES.md`
- `config/ghost_x_requirements.yaml`
- `config/ghost_x_test_catalog.yaml`
- `config/ghost_x_claims.yaml`
- `GHOST_X_TRACEABILITY.csv`
- existing hardware, software mission, and accelerated physical evidence

## Review questions

| Question | Decision |
|---|---|
| Is the engineering mission unambiguous? | YES |
| Are current evidence and unsupported claims separated? | YES |
| Are formal comparisons constrained to identical inputs and truth? | YES |
| Are quantitative acceptance targets defined before formal collection? | YES |
| Are nominal and failure scenarios predeclared? | YES |
| Are frames/timing/contracts identified as mandatory next work? | YES |
| Is controlled truth required before accuracy claims? | YES |
| Are NIS/NEES validity conditions explicit? | YES |
| Are C++/Python equivalence and software assurance required? | YES |
| Are fault, timing, resource, and CI requirements included? | YES |
| Does each controlled public claim map to requirements and tests? | YES |
| Is a no-purchase mandatory path retained? | YES |

## Findings

### Accepted strengths

1. The existing baseline is immutable and SHA-256 inventoried.
2. The system already contains real camera hardware evidence and a full deterministic observer mission.
3. Requirements distinguish software demonstration, hardware behavior, physical accuracy, consistency, and flight claims.
4. Quantitative thresholds are declared before the formal campaign.
5. The test catalog contains more than the mandatory ten fault classes.
6. Future claims are gated rather than presumed.

### Open actions

| Action | Due before | Disposition |
|---|---|---|
| Complete frame, axis, timestamp, covariance, validity, and schema contracts | G2 exit | OPEN |
| Add calibration/configuration identifiers to formal recording schema | G2 exit | OPEN |
| Freeze multi-range/orientation measurement protocol | G3 collection | OPEN |
| Define measured truth fixture and uncertainty | G4 formal trials | OPEN |
| Freeze exact G4 trial allocation totaling at least 20 accepted paired trials | G4 collection | OPEN |
| Implement C++ estimator library and Python equivalence vectors | G5 exit | OPEN |
| Establish residual-assumption checks before interpreting NIS | G6 exit | OPEN |
| Obtain external review or public benchmark before final 97/100 claim | G12 exit | OPEN |

None of these actions blocks entry into G2; each is already mapped to a requirement and verification test.

## Risk review

| Risk | Current control |
|---|---|
| Operator-created truth is less accurate than estimator error | Declare truth uncertainty; use measured fixtures; seek free external benchmark |
| Thresholds are tuned after results | Requirements/config committed before formal collection; discrepancy process required |
| Hardware demo is mistaken for autonomous flight | Claim boundary explicitly prohibits the claim |
| Covariance is treated as valid despite colored residuals | G6 validity gating and INVALID_WITH_REASON behavior |
| GHOST-MH weights are interpreted as calibrated probabilities | Current wording uses relative hypothesis weights; calibration study required |
| Pi timing claims rely on averages | G9 requires p95, p99, maximum, deadline misses, thermal and stress evidence |
| Failed trials disappear from public story | Campaign retention and final failure-gallery requirements |

## Review decision

**APPROVED TO PROCEED TO G2 — FRAMES, TIMING, AND DATA CONTRACTS.**

The review does not approve final accuracy, superiority, consistency, real-time, autonomous-flight, or production claims. Those remain gated by their mapped tests.
