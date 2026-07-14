# GHOST-X Public Failure Gallery

This gallery intentionally preserves failed assumptions, invalid statistics, injected failures, and incomplete evidence instead of presenting success-only results.

## FAIL-CONSISTENCY-001 — covariance_consistency

**Observation:** The CV and estimator position NEES means are outside the pooled textbook mean interval on the frozen campaign.

**Disposition:** Reported as model mismatch/qualification rather than tuning the result away; physical NEES remains invalid until defensible truth exists.

**Evidence:** `GHOST_X_G6_CONSISTENCY.json`

## FAIL-MULTIMODAL-NIS-001 — invalid_statistic

**Observation:** A single formal NIS is not valid for the non-Gaussian GHOST-MH mixture during multimodal intervals.

**Disposition:** The report emits INVALID_WITH_REASON and uses only qualified moment-matched diagnostics.

**Evidence:** `GHOST_X_G6_CONSISTENCY.json`

## FAIL-PHYSICAL-CAMPAIGN-001 — incomplete_evidence

**Observation:** The formal measurement-characterization and controlled physical truth campaigns are not yet collected.

**Disposition:** Software is frozen and ready; public physical-accuracy claims remain prohibited until operator-assisted collection is complete.

**Evidence:** `GHOST_X_G3_READINESS.json`

## FAULT-CAMERA-DISCONNECT — fault_injection

**Observation:** Injected camera_disconnect produced FAULT_CAMERA_DISCONNECTED.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/camera_disconnect.jsonl`

## FAULT-FROZEN-MEASUREMENT — fault_injection

**Observation:** Injected frozen_measurement produced FAULT_FROZEN_MEASUREMENT.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/frozen_measurement.jsonl`

## FAULT-DUPLICATE-MEASUREMENT — fault_injection

**Observation:** Injected duplicate_measurement produced FAULT_DUPLICATE_MEASUREMENT.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/duplicate_measurement.jsonl`

## FAULT-FALSE-DETECTION — fault_injection

**Observation:** Injected false_detection produced FAULT_FALSE_DETECTION_REJECTED.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/false_detection.jsonl`

## FAULT-COVARIANCE-CORRUPTION — fault_injection

**Observation:** Injected covariance_corruption produced FAULT_COVARIANCE_INVALID_FALLBACK.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/covariance_corruption.jsonl`

## FAULT-LATENCY — fault_injection

**Observation:** Injected latency produced FAULT_STALE_MEASUREMENT_REJECTED.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/latency.jsonl`

## FAULT-OUT-OF-SEQUENCE-DATA — fault_injection

**Observation:** Injected out_of_sequence_data produced FAULT_OUT_OF_SEQUENCE_REJECTED.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/out_of_sequence_data.jsonl`

## FAULT-NODE-RESTART — fault_injection

**Observation:** Injected node_restart produced FAULT_NODE_RESTART.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/node_restart.jsonl`

## FAULT-CPU-SATURATION — fault_injection

**Observation:** Injected cpu_saturation produced FAULT_DEADLINE_MISS.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/cpu_saturation.jsonl`

## FAULT-NETWORK-DEGRADATION — fault_injection

**Observation:** Injected network_degradation produced FAULT_NETWORK_DEGRADED.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/network_degradation.jsonl`

## FAULT-PARAMETER-MISMATCH — fault_injection

**Observation:** Injected parameter_mismatch produced FAULT_CONFIGURATION_MISMATCH.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/parameter_mismatch.jsonl`

## FAULT-LIGHTING-DEGRADATION — fault_injection

**Observation:** Injected lighting_degradation produced FAULT_LOW_VISUAL_QUALITY.

**Disposition:** Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.

**Evidence:** `g8_fault_evidence/lighting_degradation.jsonl`

## FAIL-RT-001 — runtime_requirement

**Observation:** Nominal source-to-receipt latency did not meet the predeclared bounds.

**Disposition:** Hard-real-time/performance wording is withheld; raw worst-case evidence remains public.

**Evidence:** `GHOST_X_G9_RUNTIME_REPORT.json`

## FAIL-RT-002 — runtime_requirement

**Observation:** The 30 Hz publication/deadline requirement was not met on this bench run.

**Disposition:** Hard-real-time/performance wording is withheld; raw worst-case evidence remains public.

**Evidence:** `GHOST_X_G9_RUNTIME_REPORT.json`
