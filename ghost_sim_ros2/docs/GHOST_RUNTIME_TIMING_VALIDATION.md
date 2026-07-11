# GHOST USB Timing and Raspberry Pi Runtime Validation

## Purpose

Quantify the timing and resource behavior of the physical USB UVC / Raspberry Pi pipeline during controlled trials.

These tools are prepared without hardware. Their results remain pending execution on the actual Pi and camera.

## Evidence boundaries

```text
USB timing: SOFTWARE_ARRIVAL_AND_ROS_TRANSPORT_CHARACTERIZATION
Not proven: SHUTTER_OPEN_HARDWARE_TIMESTAMP_ACCURACY

Pi resources: RUNTIME_CHARACTERIZATION_FOR_ONE_RECORDED_SESSION
Not proven: WORST_CASE_QUALIFICATION_OR_FLIGHT_COMPUTER_CERTIFICATION
```

## USB vision timing analysis

The trial recorder already stores:

- relative receive time;
- ROS receive time;
- publisher message header stamp;
- measured pose.

Analyze a trial:

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 ghost_sim_ros2/analysis/camera_timing_analysis.py \
  --vision-jsonl <trial>/vision_pose.jsonl \
  --out-dir <trial>/camera_timing
```

Outputs:

```text
camera_timing/
├── camera_timing_summary.json
├── camera_timing_summary.md
├── camera_interarrival_timeline.png
└── camera_receive_latency.png
```

Reported metrics include:

- sample count and effective rate;
- median, mean, standard deviation, 5th/95th percentile and maximum interarrival interval;
- median absolute interarrival jitter;
- long-interval/drop proxy count;
- estimated missed frame intervals;
- ROS receive time minus message header stamp when compatible timestamps exist;
- negative-latency count as a clock-definition diagnostic.

A long inter-sample interval is a dropped-interval proxy. It is not direct proof that the UVC device itself dropped a hardware frame. Receive latency includes camera/publisher, scheduling, ROS transport and timestamp-definition effects.

## Raspberry Pi resource logging

Start the resource logger immediately before a hardware run and stop it after the recorder finishes:

```bash
python3 ghost_sim_ros2/tools/runtime_resource_logger.py \
  --out-dir <trial>/runtime_resources \
  --duration-s 120 \
  --interval-s 1.0 \
  --process-patterns ghost,apriltag,ros2
```

Outputs:

```text
runtime_resources/
├── runtime_resources.csv
├── runtime_resources_summary.json
└── runtime_resources_summary.md
```

The logger uses Linux `/proc` and `/sys` sources and records:

- system CPU utilization;
- one-minute load average;
- system used/available memory;
- maximum available thermal-zone temperature;
- count of matching GHOST/AprilTag/ROS processes;
- aggregate matching-process CPU utilization;
- aggregate matching-process RSS memory.

Process matching uses command-line substrings supplied by `--process-patterns`. Review the count and pattern list before publishing a runtime claim.

## Recommended physical runs

Collect timing/resources for at least:

1. stationary controlled-R collection;
2. one representative no-occlusion motion trial;
3. one representative 3-second occlusion trial;
4. one maneuvering occlusion trial;
5. the final public hero demonstration.

The formal campaign does not need a separate resource logger for every one of 55 slots if that would interfere operationally. Instead, collect predeclared representative runtime blocks and label them accordingly.

## Publication requirements

A public runtime card must show:

- Pi and USB webcam configuration ID;
- active camera resolution, format and requested frame rate;
- trial condition and duration;
- sample count;
- median and 95th percentile values;
- maximum temperature and memory;
- process-match pattern;
- whether ROS/header-clock latency was available;
- explicit statement that the evidence is session-specific.

Do not publish a negative receive latency as a physical result without resolving the clock-definition mismatch.

## Test

```bash
PYTHONPATH=ghost_sim_ros2:ghost_sim_ros2/tools \
python3 -m pytest -q ghost_sim_ros2/test/test_runtime_timing_validation.py
```

The focused tests cover interarrival/drop detection, ROS latency extraction, percentile interpolation, synthetic `/proc` resource reads, thermal parsing, matching-process aggregation and runtime summary statistics.
