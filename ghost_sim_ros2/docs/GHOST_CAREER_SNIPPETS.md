# GHOST Career Snippets

Copy-paste friendly wording for presenting GHOST on resumes, LinkedIn, GitHub, and in interviews. These snippets describe the current evidence honestly: ROS 2 target tracking with Raspberry Pi AprilTag hardware replay artifacts, static replay tooling, and no claim of validated estimator accuracy, flight test, production deployment, or closed-loop vehicle command.

## Resume Bullets

Short one-line bullet:

- Built a ROS 2 target-tracking prototype using Raspberry Pi AprilTag measurements, with formal IMM and heuristic MH trackers replayed side by side in hardware pipeline artifacts.

Technical bullet:

- Developed a ROS 2 AprilTag target-tracking pipeline with Raspberry Pi camera input, a real formal IMM implementation, heuristic MH tracker context, live-bag plotting, and a static replay dashboard; final hardware bag `live_camera_calibrated_R_01` ran for 48.28 s with 655 vision measurements and near-30 Hz tracker odometry.

Senior/industry-style bullet:

- Owned end-to-end robotics evidence packaging for intermittent-visibility target tracking, integrating ROS 2 topics, Raspberry Pi AprilTag sensing, IMM/MH side-by-side replay, dropout-state telemetry, reproducible plots, and a dependency-free dashboard showing up to 77 IMM prediction-only steps and 2.849 s max measurement age during target loss.

## LinkedIn Project Description

GHOST is a ROS 2 target-tracking project that uses Raspberry Pi AprilTag measurements to replay a formal IMM tracker and a heuristic MH tracker side by side during intermittent visibility. The final calibrated hardware bag (`live_camera_calibrated_R_01`) produced 48.28 s of pipeline evidence with 655 vision measurements, camera poses at 13.57 Hz, and tracker odometry near 30 Hz. I packaged the results as a project report, hardware plots, and a fully static replay dashboard so reviewers can inspect measurement streams, tracker estimates, status transitions, and dropout prediction behavior without running ROS; estimator accuracy validation and statistical baseline superiority are future work.

## GitHub Pinned Repo Description

ROS 2 target-tracking prototype with Raspberry Pi AprilTag hardware replay evidence, formal IMM plus heuristic MH side-by-side telemetry, dropout prediction status, plots, report, and a static dashboard.

## Interview Talking Points

- I treated dropout as a first-class behavior: the tracker status, measurement age, and prediction-only steps are exposed instead of hidden behind a smooth-looking plot.
- I replayed a formal IMM estimator beside a heuristic MH baseline to make behavior visible during live replay and target loss; statistical comparison is pending a dedicated harness.
- I separated evidence packaging from ROS runtime so a reviewer can inspect the final hardware run through Markdown, PNG plots, exported JSON, and static HTML.
- The final evidence used a calibrated Raspberry Pi AprilTag hardware bag, not only synthetic measurements, to show end-to-end ROS 2 pipeline operation.
- I kept the PX4/drone-facing scope conservative: this package publishes target-state/setpoint topics for downstream work but does not arm or command a vehicle.
- The project reinforced how much validation depends on timestamped telemetry, explicit status labels, and reproducible artifacts.

## STAR Story

Situation: I wanted GHOST to be more than a synthetic ROS 2 tracking demo, so I needed evidence that the pipeline could process live camera measurements and behave predictably when the target disappeared.

Task: Build and package a hardware-integrated target-tracking workflow that showed raw AprilTag detections, formal IMM tracking, heuristic MH tracking, and dropout behavior in a form that other engineers could review quickly without claiming estimator accuracy before controlled R characterization.

Action: I integrated Raspberry Pi AprilTag measurements with the ROS 2 tracking pipeline, recorded the final calibrated bag, exported key odometry/status/future data, generated hardware plots, and built a dependency-free static replay dashboard and report.

Result: The final bag `live_camera_calibrated_R_01` captured 48.28 s of data with 655 vision measurements, 13.57 Hz camera pose rate, IMM/MH odometry near 30 Hz, and documented dropout behavior reaching 77 IMM prediction-only steps and 2.849 s max measurement age.

## Metrics To Mention

| Metric | Value |
| --- | ---: |
| Final bag | `live_camera_calibrated_R_01` |
| Duration | `48.28 s` |
| Vision measurements | `655` |
| Camera pose rate | `13.57 Hz` |
| IMM odom rate | `30.01 Hz` |
| MH odom rate | `29.99 Hz` |
| Max IMM prediction-only steps | `77` |
| Max IMM measurement age | `2.849 s` |

## Links To Attach

- Portfolio packet: `docs/GHOST_PORTFOLIO_PACKET.md`
- Final report: `docs/GHOST_PROJECT_REPORT.md`
- Final bag plots: `docs/GHOST_LIVE_BAG_PLOTS.md`
- Live replay dashboard: `docs/GHOST_LIVE_REPLAY_DASHBOARD.html`
