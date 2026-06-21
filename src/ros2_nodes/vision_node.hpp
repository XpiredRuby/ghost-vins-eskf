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

// Forward-declare libcamera::Request so the requestCompleted slot can be
// declared with the exact type libcamera's Signal API requires, without
// pulling the full libcamera headers into this header.
namespace libcamera { class Request; }

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// VisionNode
//
// ROS2 Humble node: AprilTag 36h11 detection and 3D pose estimation.
//
// GHOST_V12_USB_WEBCAM.md §Vision Pipeline — baseline target:
//   USB UVC webcam via V4L2 (/dev/video0), 640×480 MJPEG @ ~30 fps.
//   Camera–IMU sync: V4L2 buffer timestamp + ESKF OOSM rollback (measured latency).
//
// Current implementation note:
//   This file retains the libcamera + optional GPIO strobe code path from the
//   legacy IMX296 CSI design (GHOST_V10.md). That path is optional Phase 5
//   future work — not required for V12 USB UVC baseline bring-up.
//
// Publication layout:
//   /ghost/vision/apriltag_pose  geometry_msgs/msg/PoseStamped
//   /ghost/vision/debug_image    sensor_msgs/msg/Image (5 Hz debug only)
//
// Refuses to start if camera intrinsics in config/camera.yaml are still 0.0
// (uncalibrated). Run camera calibration first (Phase 2 exit criterion).
//
// Parameters (from config/camera.yaml via ROS2 parameter server):
//   decimation.width_px, decimation.height_px, decimation.factor
//   roi.width_px, roi.height_px
//   timestamp.strobe_gpio, timestamp.strobe_enabled  (strobe: optional upgrade only)
//   sensor.max_exposure_ms
//   intrinsics.fx, fy, cx, cy — MUST be calibrated at capture resolution
//   apriltag.tag_size_m, apriltag.tag_id
// ─────────────────────────────────────────────────────────────────────────────
class VisionNode : public rclcpp::Node {
public:
    explicit VisionNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions{});
    ~VisionNode() override;

    // Open camera backend, configure stream, allocate buffers.
    // Optional: arm GPIO strobe ISR when timestamp.strobe_enabled (IMX296 Phase 5 upgrade).
    // Throws std::runtime_error on hardware failure.
    void initialize();

private:
    // ── Camera callback (called from libcamera internal thread) ───────────────
    // requestCompleted slot — libcamera's Signal API requires an object pointer
    // and a member function pointer (it does not accept a bare lambda). This
    // thin slot forwards to onFrameReady(); see vision_node.cpp.
    void onFrameReadySlot(libcamera::Request* request);

    // Forward-declared to avoid pulling libcamera headers into this header.
    // Defined in the .cpp after the libcamera-guarded include block.
    void onFrameReady(void* request_ptr);

    // ── Per-frame processing (runs inside onFrameReady) ───────────────────────
    void processFrame(const uint8_t* y_plane, int width, int height,
                      uint64_t timestamp_us);

    // ── Optional GPIO strobe thread (IMX296 Phase 5 upgrade only) ───────────
    // GHOST_V12: baseline uses V4L2 timestamp + ESKF OOSM — strobe not required.
    // GHOST_V10.md (legacy): IMX296 Strobe → GPIO22 ISR at shutter-open.
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

    // ── Calibrated intrinsics (K_scaled = K_intrinsic / decimation_factor) ───
    // GHOST_V12: scale K for capture/decimation resolution — wrong K → wrong depth
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
