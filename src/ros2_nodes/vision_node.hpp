#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <sensor_msgs/msg/image.hpp>

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// VisionNode
//
// ROS2 Humble node that captures frames from the IMX296 global shutter camera
// via the direct libcamera API, detects AprilTag 36h11 tags, estimates 3D pose,
// and publishes detections for the target tracker node.
//
// GHOST_V10.md §Vision Pipeline:
//   Capture at 728×544 (decimated from 1456×1088 native resolution).
//   Hardware timestamp via GPIO22 strobe ISR — eliminates V4L2 15–40ms latency.
//   Two-tier detection: full decimated frame (Tier 1) or 300×300 ROI (Tier 2).
//   K_decimated = K_intrinsic / 2  (ALL four intrinsic params divided by 2).
//
// Publication layout:
//   /ghost/vision/apriltag_pose  geometry_msgs/msg/PoseStamped
//       Tag pose in camera frame, hardware-timestamped at shutter-open.
//   /ghost/vision/debug_image    sensor_msgs/msg/Image
//       Annotated mono8 frame at 5 Hz — for debugging only, not consumed by tracker.
//
// Refuses to start if camera intrinsics in config/camera.yaml are still 0.0
// (uncalibrated). Run camera calibration first (Phase 2 exit criterion).
//
// Parameters (from config/camera.yaml via ROS2 parameter server):
//   decimation.width_px                  int    728
//   decimation.height_px                 int    544
//   decimation.factor                    int    2
//   roi.width_px                         int    300
//   roi.height_px                        int    300
//   timestamp.strobe_gpio                int    22
//   sensor.max_exposure_ms               double 3.0
//   intrinsics.fx, fy, cx, cy           double 0.0   — MUST be calibrated
//   intrinsics.distortion.k1,k2,p1,p2   double 0.0   — MUST be calibrated
//   apriltag.tag_size_m                  double 0.10
//   apriltag.tag_id                      int    0
// ─────────────────────────────────────────────────────────────────────────────
class VisionNode : public rclcpp::Node {
public:
    explicit VisionNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions{});
    ~VisionNode() override;

    // Open libcamera, configure stream, allocate buffers, arm strobe ISR,
    // and start capture loop. Throws std::runtime_error on hardware failure.
    void initialize();

private:
    // ── Camera callback (called from libcamera internal thread) ───────────────
    // Forward-declared to avoid pulling libcamera headers into this header.
    // Defined in the .cpp after the libcamera-guarded include block.
    void onFrameReady(void* request_ptr);

    // ── Per-frame processing (runs inside onFrameReady) ───────────────────────
    void processFrame(const uint8_t* y_plane, int width, int height,
                      uint64_t timestamp_us);

    // ── GPIO22 strobe thread — latches CLOCK_MONOTONIC at shutter-open ───────
    // GHOST_V10.md: "V4L2 timestamps at userspace buffer arrival — 15–40ms late"
    // Fix: IMX296 Strobe → GPIO22 ISR latches CLOCK_MONOTONIC at shutter-open.
    void strobeThread();

    // ── Debug image timer — 5 Hz ──────────────────────────────────────────────
    void debugTimerCallback();

    // ── Camera and AprilTag state — pimpl to keep libcamera/C headers out ────
    // Full struct definitions live in vision_node.cpp after the guarded includes.
    struct CameraState;
    struct AprilTagState;
    std::unique_ptr<CameraState>    cam_;
    std::unique_ptr<AprilTagState>  at_;

    // ── Hardware strobe timestamp ring buffer (Issue 7 fix) ──────────────────
    // A single atomic<uint64_t> is overwritten by every strobe edge.  At high
    // frame rates the strobe for frame N+1 can overwrite the slot before the
    // libcamera callback for frame N runs, assigning the wrong timestamp.
    //
    // Fix: lock-free SPSC ring of 8 slots.
    //   Producer (strobeThread): writes head slot, increments head (release).
    //   Consumer (onFrameReady):  reads tail slot, increments tail (release).
    //   At 45 fps this absorbs up to 8 frames (~180 ms) of callback latency.
    //
    // Invariant: kStrobeBufSize must be a power of two (index mask = size-1).
    static constexpr uint32_t kStrobeBufSize = 8;
    std::array<uint64_t, kStrobeBufSize> strobe_ring_{};
    std::atomic<uint32_t>                strobe_head_{0};  // producer writes
    std::atomic<uint32_t>                strobe_tail_{0};  // consumer reads

    std::thread      strobe_thread_;
    std::atomic<bool> strobe_running_{false};
    int               strobe_gpio_fd_{-1};  // GPIO line event fd

    // ── Latest frame copy for debug image publisher ───────────────────────────
    mutable std::mutex           debug_mutex_;
    std::vector<uint8_t>         debug_frame_;
    int                          debug_width_{0};
    int                          debug_height_{0};

    // ── Publishers ────────────────────────────────────────────────────────────
    rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr         debug_pub_;

    // ── Debug timer ───────────────────────────────────────────────────────────
    rclcpp::TimerBase::SharedPtr debug_timer_;

    // ── Calibrated intrinsics (K_decimated = K_intrinsic / decimation_factor) ─
    // GHOST_V10.md: "K_decimated = K/2 — using K_intrinsic reports 2× depth"
    double fx_dec_{0.0}, fy_dec_{0.0};
    double cx_dec_{0.0}, cy_dec_{0.0};

    // ── Parameters ────────────────────────────────────────────────────────────
    int    dec_width_{728};
    int    dec_height_{544};
    int    roi_width_{300};
    int    roi_height_{300};
    int    strobe_gpio_{22};
    int    target_tag_id_{0};
    double tag_size_m_{0.10};
    double max_exposure_ms_{3.0};
};

}  // namespace ghost
