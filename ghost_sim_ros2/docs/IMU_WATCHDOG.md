# GHOST MPU-6050 Watchdog Evidence

## Result
The Raspberry Pi successfully detected and read the MPU-6050 over I2C at address 0x68.

The watchdog produced stable readings during rest and correctly flagged motion events.

## Static Calibration
- Accel norm baseline: 0.98696 g
- Gyro bias: [-1.69879, -0.49876, -1.10303] deg/s

## Watchdog Demo
- STABLE samples: 180
- CAMERA_SUSPECT samples: 5
- CAMERA_BUMPED samples: 2
- Max gyro magnitude: 116.55 deg/s
- Max accel delta: 0.116 g

## Interpretation
The MPU-6050 watchdog can detect camera/tripod disturbance events and return to STABLE afterward.
This validates the physical IMU hardware path for GHOST.
