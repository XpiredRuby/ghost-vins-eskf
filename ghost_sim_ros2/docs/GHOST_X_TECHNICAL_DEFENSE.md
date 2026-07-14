# GHOST-X 10-Minute Technical Defense

## 0:00–1:00 — Problem and requirements

Explain why visibility loss, model mismatch, latency, false detections, and resource limits make target tracking an estimation-and-assurance problem rather than only a computer-vision demo. Show the requirements-to-test structure and claim gates.

## 1:00–2:15 — Data contracts and evidence discipline

Define frames, SI units, source/receipt/processing/publication timestamps, covariance conventions, calibration/configuration hashes, validity states, and stale-data behavior. Explain why these contracts precede statistical comparison.

## 2:15–3:45 — Estimators

Derive the CV state transition and white-acceleration process covariance. Walk through the five IMM stages: predicted mode probabilities, destination-conditioned mixing, mode-matched prediction/update, Gaussian likelihood update, and moment-matched combination. Contrast this with GHOST-MH’s persistent labeled hypotheses and relative weights.

## 3:45–5:00 — C++ assurance and equivalence

Show the ROS-independent Eigen library, Joseph covariance update, deterministic configuration parser, covariance PSD/symmetry properties, sanitizer run, and frozen C++/Python equivalence. State that equivalence proves implementation agreement, not model truth.

## 5:00–6:15 — Controlled truth, consistency, and trade study

Show 24 analytic-truth trials and identical stream hashes. Present visible, hidden, future, recovery, and compute metrics. Explain why IMM NIS is only moment-matched and why one scalar formal NIS is invalid for a multimodal GHOST-MH belief. Show parameter selection rules declared before ranking.

## 6:15–7:20 — Fault injection

Present the 12-fault matrix. For one example, trace source timestamp, monitor decision, isolation gate, estimator input, degraded status, and recovery. Explain why raw rejected evidence is retained.

## 7:20–8:20 — DDS and Pi runtime

Compare reliable and best-effort QoS, depth, deadline, liveliness, incompatibility, overload, and CPU stress. Report p95/p99/max rather than averages only. Distinguish estimator execution deadline evidence from operating-system hard-real-time guarantees.

## 8:20–9:10 — Determinism and CI

Show repeated tree hashes, acceptance bands, deliberate negative hash/metric tests, C++ tests, Python tests, and GitHub artifact export. Explain what changes make CI fail.

## 9:10–10:00 — Limitations and next experiment

State that G3/G4 physical collection is pending; room geometry is not certified metrology; no physical accuracy, VIO/SLAM, PX4, flight qualification, or universal GHOST-MH superiority is claimed. Finish with the exact first G3 setup and how its result will update covariance selection and physical claim gates.
