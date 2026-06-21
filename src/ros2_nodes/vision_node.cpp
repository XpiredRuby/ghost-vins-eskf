// ─────────────────────────────────────────────────────────────────────────────
// vision_node.cpp
// GHOST §Vision Pipeline — USB UVC baseline (V12); libcamera path = optional IMX296 upgrade
// ─────────────────────────────────────────────────────────────────────────────

// Dependency guards: emit a descriptive #error rather than cryptic link failures
// if the optional hardware libraries are missing from the build environment.

#if !__has_include(<libcamera/libcamera.h>)
#  error "libcamera not found. Install with: sudo apt install libcamera-dev"\
         "  (optional IMX296 CSI upgrade path — see GHOST_V12_USB_WEBCAM.md §Optional Hardware Upgrade)."
#endif

#if !__has_include(<apriltag/apriltag.h>)
#  error "apriltag C library not found. Install with: sudo apt install libapriltag-dev"
#endif

// ── libcamera ─────────────────────────────────────────────────────────────────
#include <libcamera/libcamera.h>

// ── AprilTag (C library — needs extern "C") ───────────────────────────────────
extern "C" {
#include <apriltag/apriltag.h>
#include <apriltag/tag36h11.h>
#include <apriltag/apriltag_pose.h>
}

// ── Linux kernel APIs ─────────────────────────────────────────────────────────
#include <fcntl.h>
#include <linux/gpio.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

// ── Standard C++ ──────────────────────────────────────────────────────────────
#include <algorithm>
#include <cmath>
#include <cstring>
#include <map>
#include <stdexcept>
#include <string>

// ── Eigen (quaternion from rotation matrix only) ───────────────────────────────
#include <Eigen/Geometry>

// ── ROS2 ──────────────────────────────────────────────────────────────────────
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/vector3.hpp>
#include <rclcpp/rclcpp.hpp>

#include "ros2_nodes/vision_node.hpp"

// ─────────────────────────────────────────────────────────────────────────────
// Pimpl structs — definitions live here, after guarded includes
// ─────────────────────────────────────────────────────────────────────────────
namespace ghost {

// ── libcamera state ───────────────────────────────────────────────────────────
struct VisionNode::CameraState {
    std::unique_ptr<libcamera::CameraManager>   manager;
    std::shared_ptr<libcamera::Camera>          camera;
    std::unique_ptr<libcamera::CameraConfiguration> config;
    std::unique_ptr<libcamera::FrameBufferAllocator> allocator;
    libcamera::Stream*                          stream{nullptr};

    // Requests kept alive for the capture loop
    std::vector<std::unique_ptr<libcamera::Request>> requests;

    // Mmap mappings — allocated once at init, reused each frame (no hot-path heap).
    // base/map_size are the raw mmap arguments for munmap.
    // data is base + plane.offset — the actual start of Y pixel data.
    struct MappedBuf {
        void*    base{MAP_FAILED};
        size_t   map_size{0};
        uint8_t* data{nullptr};   // base + plane.offset
    };
    std::map<const libcamera::FrameBuffer*, MappedBuf> mapped;
};

// ── AprilTag detector state ───────────────────────────────────────────────────
struct VisionNode::AprilTagState {
    apriltag_family_t*   family{nullptr};
    apriltag_detector_t* detector{nullptr};
};

// ─────────────────────────────────────────────────────────────────────────────
// Constructor
// ─────────────────────────────────────────────────────────────────────────────
VisionNode::VisionNode(const rclcpp::NodeOptions& options)
: rclcpp::Node("vision_node", options)
{
    // ── Declare parameters (all sourced from config/camera.yaml) ──────────────
    declare_parameter("decimation.width_px",          728);
    declare_parameter("decimation.height_px",         544);
    declare_parameter("decimation.factor",            2);
    declare_parameter("roi.width_px",                 300);
    declare_parameter("roi.height_px",                300);
    declare_parameter("timestamp.strobe_gpio",        22);
    declare_parameter("timestamp.strobe_enabled",     false);  // V12: false — OOSM baseline
    declare_parameter("sensor.max_exposure_ms",       3.0);
    declare_parameter("intrinsics.fx",                0.0);
    declare_parameter("intrinsics.fy",                0.0);
    declare_parameter("intrinsics.cx",                0.0);
    declare_parameter("intrinsics.cy",                0.0);
    declare_parameter("intrinsics.distortion.k1",     0.0);
    declare_parameter("intrinsics.distortion.k2",     0.0);
    declare_parameter("intrinsics.distortion.p1",     0.0);
    declare_parameter("intrinsics.distortion.p2",     0.0);
    declare_parameter("apriltag.tag_size_m",          0.10);
    declare_parameter("apriltag.tag_id",              0);

    // ── Read parameters ───────────────────────────────────────────────────────
    dec_width_       = get_parameter("decimation.width_px").as_int();
    dec_height_      = get_parameter("decimation.height_px").as_int();
    roi_width_       = get_parameter("roi.width_px").as_int();
    roi_height_      = get_parameter("roi.height_px").as_int();
    strobe_gpio_     = get_parameter("timestamp.strobe_gpio").as_int();
    max_exposure_ms_ = get_parameter("sensor.max_exposure_ms").as_double();
    target_tag_id_   = get_parameter("apriltag.tag_id").as_int();
    tag_size_m_      = get_parameter("apriltag.tag_size_m").as_double();

    const int dec_factor = get_parameter("decimation.factor").as_int();
    const double fx_native = get_parameter("intrinsics.fx").as_double();
    const double fy_native = get_parameter("intrinsics.fy").as_double();
    const double cx_native = get_parameter("intrinsics.cx").as_double();
    const double cy_native = get_parameter("intrinsics.cy").as_double();

    // ── Calibration guard ─────────────────────────────────────────────────────
    // GHOST_V12 §Vision Pipeline: Phase 2 exit criterion is reprojection < 0.5 px.
    if (fx_native == 0.0 || fy_native == 0.0) {
        RCLCPP_ERROR(get_logger(),
            "Camera not calibrated — run calibration first. "
            "intrinsics.fx and/or intrinsics.fy are 0.0 in config/camera.yaml. "
            "See GHOST_V12_USB_WEBCAM.md §Development Phases — Phase 2.");
        throw std::runtime_error("vision_node: camera not calibrated");
    }

    // ── K_scaled = K_intrinsic / decimation_factor ────────────────────────────
    // GHOST_V12: using unscaled K on a decimated frame reports wrong depth
    const double df = static_cast<double>(dec_factor);
    fx_dec_ = fx_native / df;
    fy_dec_ = fy_native / df;
    cx_dec_ = cx_native / df;
    cy_dec_ = cy_native / df;

    // ── Publishers ────────────────────────────────────────────────────────────
    pose_pub_  = create_publisher<geometry_msgs::msg::PoseStamped>(
        "/ghost/vision/apriltag_pose", rclcpp::SensorDataQoS{});
    debug_pub_ = create_publisher<sensor_msgs::msg::Image>(
        "/ghost/vision/debug_image", rclcpp::SensorDataQoS{});

    // ── Debug image timer — 5 Hz (not used by tracker, for human verification) ─
    debug_timer_ = create_wall_timer(
        std::chrono::milliseconds(200),
        std::bind(&VisionNode::debugTimerCallback, this));

    // ── Allocate pimpl structs ─────────────────────────────────────────────────
    cam_ = std::make_unique<CameraState>();
    at_  = std::make_unique<AprilTagState>();

    RCLCPP_INFO(get_logger(),
        "vision_node constructed: %dx%d decimated, ROI %dx%d, "
        "fx=%.2f fy=%.2f cx=%.2f cy=%.2f (K_decimated)",
        dec_width_, dec_height_, roi_width_, roi_height_,
        fx_dec_, fy_dec_, cx_dec_, cy_dec_);
}

// ─────────────────────────────────────────────────────────────────────────────
// Destructor
// ─────────────────────────────────────────────────────────────────────────────
VisionNode::~VisionNode()
{
    // Signal strobe thread and wake it by closing the fd
    strobe_running_.store(false, std::memory_order_relaxed);
    if (strobe_gpio_fd_ >= 0) {
        close(strobe_gpio_fd_);
        strobe_gpio_fd_ = -1;
    }
    if (strobe_thread_.joinable()) strobe_thread_.join();

    // Stop camera — strict teardown order required by libcamera:
    //   stop() → clear Requests → unmap → deallocate → release → manager stop
    if (cam_ && cam_->camera) {
        cam_->camera->stop();
        cam_->requests.clear();                   // must precede allocator teardown
        for (auto& [buf, mb] : cam_->mapped) {
            if (mb.base != MAP_FAILED) ::munmap(mb.base, mb.map_size);
        }
        cam_->mapped.clear();
        cam_->allocator.reset();
        cam_->camera->release();
        cam_->camera.reset();
        cam_->manager->stop();
    }

    // Tear down AprilTag detector
    if (at_) {
        if (at_->detector) apriltag_detector_destroy(at_->detector);
        if (at_->family)   tag36h11_destroy(at_->family);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// initialize() — hardware setup (not in constructor per GHOST node convention)
// ─────────────────────────────────────────────────────────────────────────────
void VisionNode::initialize()
{
    // ── 1. AprilTag detector ──────────────────────────────────────────────────
    at_->family   = tag36h11_create();
    at_->detector = apriltag_detector_create();
    // quad_decimate=1.0: no additional decimation on the already-decimated frame
    at_->detector->quad_decimate = 1.0f;
    at_->detector->nthreads      = 2;
    at_->detector->debug         = 0;
    apriltag_detector_add_family(at_->detector, at_->family);
    RCLCPP_INFO(get_logger(), "AprilTag detector ready (36h11, tag size %.2f m)", tag_size_m_);

    // ── 2. Optional GPIO strobe thread (IMX296 Phase 5 upgrade only) ──────────
    // V12 baseline: camera–IMU sync via V4L2 timestamp + ESKF OOSM — skip when disabled.
    const bool strobe_enabled = get_parameter("timestamp.strobe_enabled").as_bool();
    if (strobe_enabled) {
        int chip_fd = open("/dev/gpiochip0", O_RDWR | O_CLOEXEC);
        if (chip_fd < 0) {
            throw std::runtime_error("vision_node: cannot open /dev/gpiochip0 for strobe GPIO");
        }

        gpio_v2_line_request req{};
        req.offsets[0]      = static_cast<uint32_t>(strobe_gpio_);
        req.num_lines       = 1;
        req.config.flags    = GPIO_V2_LINE_FLAG_INPUT | GPIO_V2_LINE_FLAG_EDGE_RISING;
        std::snprintf(req.consumer, sizeof(req.consumer), "ghost_vision_strobe");

        if (ioctl(chip_fd, GPIO_V2_GET_LINE_IOCTL, &req) < 0) {
            close(chip_fd);
            throw std::runtime_error("vision_node: cannot request GPIO22 for strobe edge detection");
        }
        close(chip_fd);
        strobe_gpio_fd_ = req.fd;

        strobe_running_.store(true, std::memory_order_relaxed);
        strobe_thread_ = std::thread(&VisionNode::strobeThread, this);
        RCLCPP_INFO(get_logger(),
            "GPIO strobe ISR enabled on GPIO%d (IMX296 optional upgrade path)",
            strobe_gpio_);
    } else {
        RCLCPP_INFO(get_logger(),
            "GPIO strobe disabled — V12 baseline uses V4L2 timestamp + ESKF OOSM");
    }

    // ── 3. libcamera — open camera (optional IMX296 CSI upgrade backend) ────
    cam_->manager = std::make_unique<libcamera::CameraManager>();
    if (cam_->manager->start() != 0) {
        throw std::runtime_error("vision_node: libcamera CameraManager::start() failed");
    }

    auto cameras = cam_->manager->cameras();
    if (cameras.empty()) {
        throw std::runtime_error("vision_node: no cameras found by libcamera");
    }
    cam_->camera = cameras[0];
    RCLCPP_INFO(get_logger(), "libcamera: using camera '%s'", cam_->camera->id().c_str());

    if (cam_->camera->acquire() != 0) {
        throw std::runtime_error("vision_node: cannot acquire camera");
    }

    // ── 4. Configure stream at decimated resolution (728×544, YUV420) ────────
    cam_->config = cam_->camera->generateConfiguration({libcamera::StreamRole::Viewfinder});
    if (!cam_->config) {
        throw std::runtime_error("vision_node: generateConfiguration() failed");
    }

    libcamera::StreamConfiguration& scfg = cam_->config->at(0);
    scfg.pixelFormat = libcamera::formats::YUV420;  // Y plane → grayscale for AprilTag
    scfg.size        = {static_cast<unsigned>(dec_width_),
                        static_cast<unsigned>(dec_height_)};
    scfg.bufferCount = 4;  // triple-buffer + 1 to avoid producer stall

    {
        const auto status = cam_->config->validate();
        if (status == libcamera::CameraConfiguration::Invalid) {
            throw std::runtime_error("vision_node: camera configuration is invalid");
        }
        if (status == libcamera::CameraConfiguration::Adjusted) {
            // libcamera silently changed size or pixel format to the nearest supported
            // value.  dec_width_/dec_height_ must be updated or every downstream
            // calculation (mmap size, ROI centre, stride) will use wrong dimensions.
            RCLCPP_WARN(get_logger(),
                "libcamera adjusted camera config — requested %dx%d, got %dx%d %s. "
                "Update config/camera.yaml if this format differs from the spec.",
                dec_width_, dec_height_,
                cam_->config->at(0).size.width,
                cam_->config->at(0).size.height,
                cam_->config->at(0).pixelFormat.toString().c_str());
        }
    }

    if (cam_->camera->configure(cam_->config.get()) != 0) {
        throw std::runtime_error("vision_node: camera->configure() failed");
    }

    // Authoritative dimensions come from the configured stream, not our requests.
    dec_width_  = static_cast<int>(cam_->config->at(0).size.width);
    dec_height_ = static_cast<int>(cam_->config->at(0).size.height);

    cam_->stream = cam_->config->at(0).stream();
    RCLCPP_INFO(get_logger(), "libcamera configured: %dx%d %s",
        dec_width_, dec_height_,
        cam_->config->at(0).pixelFormat.toString().c_str());

    // ── 5. Allocate frame buffers and mmap once (no hot-path allocation) ──────
    cam_->allocator = std::make_unique<libcamera::FrameBufferAllocator>(cam_->camera);
    if (cam_->allocator->allocate(cam_->stream) < 0) {
        throw std::runtime_error("vision_node: FrameBufferAllocator::allocate() failed");
    }

    for (const auto& buf : cam_->allocator->buffers(cam_->stream)) {
        const libcamera::FrameBuffer::Plane& plane = buf->planes()[0];
        // mmap the full range [0, offset+length) so the Y data at plane.offset
        // is accessible regardless of where within the DMA-buf it sits.
        const size_t map_size = static_cast<size_t>(plane.offset) + plane.length;
        void* base = ::mmap(nullptr, map_size, PROT_READ, MAP_SHARED,
                            plane.fd.get(), 0);
        if (base == MAP_FAILED) {
            throw std::runtime_error("vision_node: mmap() failed for frame buffer");
        }
        cam_->mapped[buf.get()] = {
            base,
            map_size,
            static_cast<uint8_t*>(base) + plane.offset   // data ptr
        };
    }

    // ── 6. Build capture requests ─────────────────────────────────────────────
    for (const auto& buf : cam_->allocator->buffers(cam_->stream)) {
        auto request = cam_->camera->createRequest();
        if (!request) {
            throw std::runtime_error("vision_node: createRequest() failed");
        }
        if (request->addBuffer(cam_->stream, buf.get()) != 0) {
            throw std::runtime_error("vision_node: Request::addBuffer() failed");
        }
        cam_->requests.push_back(std::move(request));
    }

    // ── 7. Wire up request-completed signal ───────────────────────────────────
    // libcamera signals are invoked from the camera manager's internal thread.
    // We do all heavy work (AprilTag detection) directly in the callback since
    // the single-threaded ROS2 executor is not involved here.
    // libcamera 0.3.2's Signal::connect() requires an object pointer + member
    // function pointer; it does not accept a bare lambda. onFrameReadySlot()
    // forwards to onFrameReady().
    cam_->camera->requestCompleted.connect(this, &VisionNode::onFrameReadySlot);

    // ── 8. Apply exposure control and start capture ───────────────────────────
    // GHOST_V12 §Vision Pipeline: "Exposure as short as practicable" (rolling shutter)
    // AeEnable and ExposureTime are contradictory: when AE is enabled, the ISP
    // pipeline owns ExposureTime and silently overrides any value we set, defeating
    // the 3ms motion-blur cap.  Fix: disable AE and use fixed exposure.
    // Construct ControlList from the camera's own ControlInfoMap so set() is
    // validated against what this hardware actually supports.
    libcamera::ControlList controls(cam_->camera->controls());
    controls.set(libcamera::controls::AeEnable, false);
    controls.set(libcamera::controls::ExposureTime,
                 static_cast<int32_t>(max_exposure_ms_ * 1000.0));

    if (cam_->camera->start(&controls) != 0) {
        throw std::runtime_error("vision_node: camera->start() failed");
    }

    // Queue all requests to prime the pipeline
    for (auto& req : cam_->requests) {
        cam_->camera->queueRequest(req.get());
    }

    RCLCPP_INFO(get_logger(),
        "vision_node initialized: capturing %dx%d YUV420, target 25–45 fps",
        dec_width_, dec_height_);
}

// ─────────────────────────────────────────────────────────────────────────────
// strobeThread — optional IMX296 Phase 5 upgrade: GPIO rising-edge kernel timestamp
// GHOST_V10.md (legacy): "IMX296 Strobe pin → GPIO22 ISR → CLOCK_MONOTONIC at shutter-open"
// GHOST_V12 baseline does not require this thread (timestamp.strobe_enabled: false).
// ─────────────────────────────────────────────────────────────────────────────
void VisionNode::strobeThread()
{
    pollfd pfd{strobe_gpio_fd_, POLLIN, 0};

    while (strobe_running_.load(std::memory_order_relaxed)) {
        const int ret = poll(&pfd, 1, 200);  // 200 ms timeout — 5fps worst case
        if (ret < 0) break;  // fd was closed in destructor
        if (ret == 0) continue;  // timeout, no strobe — camera may be starting

        gpio_v2_line_event event{};
        if (read(strobe_gpio_fd_, &event, sizeof(event)) != sizeof(event)) break;

        if (event.id == GPIO_V2_LINE_EVENT_RISING_EDGE) {
            // SPSC push: write slot, then advance head with release so the
            // consumer sees the payload before it sees the updated head.
            const uint32_t head = strobe_head_.load(std::memory_order_relaxed);
            const uint32_t tail = strobe_tail_.load(std::memory_order_acquire);
            if ((head - tail) < kStrobeBufSize) {
                strobe_ring_[head & (kStrobeBufSize - 1)] = event.timestamp_ns;
                strobe_head_.store(head + 1, std::memory_order_release);
            }
            // else: ring full (>8 frames of callback backlog) — drop silently.
            // This cannot happen at ≤45 fps unless the libcamera thread is
            // completely stalled; in that case timestamps are the least concern.
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// onFrameReadySlot — libcamera requestCompleted slot (object+member fn pointer).
// Thin forwarder so the header can stay free of libcamera includes (onFrameReady
// takes void* and is the implementation; this slot supplies the typed signature
// that libcamera::Signal::connect() requires).
// ─────────────────────────────────────────────────────────────────────────────
void VisionNode::onFrameReadySlot(libcamera::Request* request)
{
    onFrameReady(static_cast<void*>(request));
}

// ─────────────────────────────────────────────────────────────────────────────
// onFrameReady — libcamera callback, runs on camera manager's internal thread
// ─────────────────────────────────────────────────────────────────────────────
void VisionNode::onFrameReady(void* request_ptr)
{
    auto* request = static_cast<libcamera::Request*>(request_ptr);

    if (request->status() == libcamera::Request::RequestCancelled) return;

    // SPSC pop: consume the oldest unread strobe timestamp for this frame.
    // Each strobe edge is pushed by strobeThread() exactly once and consumed
    // here exactly once — one entry per frame, in FIFO order.
    // Falls back to 0 (will use now() downstream) if the ring is empty,
    // which can happen during the first frame before the strobe fires.
    uint64_t strobe_ns = 0;
    {
        const uint32_t head = strobe_head_.load(std::memory_order_acquire);
        const uint32_t tail = strobe_tail_.load(std::memory_order_relaxed);
        if (head != tail) {
            strobe_ns = strobe_ring_[tail & (kStrobeBufSize - 1)];
            strobe_tail_.store(tail + 1, std::memory_order_release);
        }
    }
    const uint64_t timestamp_us = (strobe_ns > 0) ? strobe_ns / 1000ULL : 0ULL;

    // Retrieve the frame buffer
    const libcamera::FrameBuffer* buffer =
        request->buffers().begin()->second;

    const auto it = cam_->mapped.find(buffer);
    if (it != cam_->mapped.end() && it->second.base != MAP_FAILED) {
        // YUV420: Y plane starts at it->second.data (base + plane.offset).
        processFrame(it->second.data, dec_width_, dec_height_, timestamp_us);
    }

    // Recycle the request — required before re-queuing
    request->reuse(libcamera::Request::ReuseBuffers);
    if (cam_->camera->queueRequest(request) != 0) {
        // Non-fatal: camera may be stopping. WARN_ONCE avoids log spam per frame.
        RCLCPP_WARN_ONCE(get_logger(),
            "queueRequest() failed — camera may be stopping or request was cancelled");
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// processFrame — AprilTag detection on the cropped ROI
// ─────────────────────────────────────────────────────────────────────────────
void VisionNode::processFrame(const uint8_t* y_plane, int width, int height,
                               uint64_t timestamp_us)
{
    // GHOST_V12 §Vision Pipeline: Tier 1 ROI centred on frame; Tier 2 at predicted pixel — TODO.
    const int roi_x0 = std::max(0, (width  - roi_width_)  / 2);
    const int roi_y0 = std::max(0, (height - roi_height_) / 2);
    const int roi_w  = std::min(roi_width_,  width  - roi_x0);
    const int roi_h  = std::min(roi_height_, height - roi_y0);

    // Build a contiguous grayscale ROI buffer (no heap in hot path: use thread_local)
    thread_local std::vector<uint8_t> roi_buf;
    roi_buf.resize(static_cast<size_t>(roi_w * roi_h));

    for (int row = 0; row < roi_h; ++row) {
        const uint8_t* src = y_plane + (roi_y0 + row) * width + roi_x0;
        uint8_t*       dst = roi_buf.data() + row * roi_w;
        std::memcpy(dst, src, static_cast<size_t>(roi_w));
    }

    // ── AprilTag detection ────────────────────────────────────────────────────
    image_u8_t im{roi_w, roi_h, roi_w, roi_buf.data()};
    zarray_t* detections = apriltag_detector_detect(at_->detector, &im);

    // ── Update debug frame (full decimated Y plane, annotated with corners) ───
    {
        std::lock_guard<std::mutex> lock(debug_mutex_);
        debug_width_  = width;
        debug_height_ = height;
        debug_frame_.assign(y_plane, y_plane + width * height);

        // Draw a simple 5×5 cross at each detected tag corner (no dependency on CV)
        for (int i = 0; i < zarray_size(detections); ++i) {
            apriltag_detection_t* det;
            zarray_get(detections, i, &det);
            for (int c = 0; c < 4; ++c) {
                const int px = static_cast<int>(det->p[c][0]) + roi_x0;
                const int py = static_cast<int>(det->p[c][1]) + roi_y0;
                for (int dy = -2; dy <= 2; ++dy) {
                    for (int dx = -2; dx <= 2; ++dx) {
                        const int qx = std::clamp(px + dx, 0, width  - 1);
                        const int qy = std::clamp(py + dy, 0, height - 1);
                        debug_frame_[qy * width + qx] = 255;  // white marker
                    }
                }
            }
        }
    }

    // ── Per-detection: pose estimation and publishing ─────────────────────────
    bool published_any = false;
    for (int i = 0; i < zarray_size(detections); ++i) {
        apriltag_detection_t* det;
        zarray_get(detections, i, &det);

        if (det->id != target_tag_id_) continue;

        // Pose estimation using K_decimated intrinsics
        apriltag_detection_info_t info{};
        info.det     = det;
        info.tagsize = tag_size_m_;
        info.fx      = fx_dec_;
        info.fy      = fy_dec_;
        info.cx      = cx_dec_ - static_cast<double>(roi_x0);  // ROI offset correction
        info.cy      = cy_dec_ - static_cast<double>(roi_y0);

        apriltag_pose_t pose{};
        const double reproj_err = estimate_tag_pose(&info, &pose);

        // matd_destroy() is not exported from libapriltag 3.2.0 on Ubuntu 22.04.
        // pose.R and pose.t are stack-local pointers — memory is managed internally
        // by the apriltag library and freed when the detection is destroyed.

        // Gate on reprojection error. A large or non-finite value means the tag
        // corners were degenerate (motion blur, partial occlusion, oblique angle).
        // Publishing such a pose to the tracker would inject a spike into the KF.
        // Threshold 2.0 px is tunable — tighten once calibration is complete.
        if (!std::isfinite(reproj_err) || reproj_err > 2.0) {
            RCLCPP_WARN(get_logger(),
                "Tag %d: reprojection error %.2f px exceeds gate — pose discarded",
                target_tag_id_, reproj_err);
            continue;
        }

        // Extract translation (metres, camera frame)
        const double tx = MATD_EL(pose.t, 0, 0);
        const double ty = MATD_EL(pose.t, 1, 0);
        const double tz = MATD_EL(pose.t, 2, 0);

        // Convert 3×3 rotation matrix to quaternion via Eigen
        Eigen::Matrix3d R;
        for (int r = 0; r < 3; ++r)
            for (int c = 0; c < 3; ++c)
                R(r, c) = MATD_EL(pose.R, r, c);
        const Eigen::Quaterniond q(R);

        // Publish PoseStamped (tag pose in camera frame)
        geometry_msgs::msg::PoseStamped msg{};
        if (timestamp_us > 0) {
            // Optional strobe timestamp (IMX296 upgrade); else downstream uses now()
            msg.header.stamp = rclcpp::Time(
                static_cast<int64_t>(timestamp_us * 1000ULL));  // ns
        } else {
            msg.header.stamp = now();
        }
        msg.header.frame_id = "camera_link";

        msg.pose.position.x = tx;
        msg.pose.position.y = ty;
        msg.pose.position.z = tz;
        msg.pose.orientation.w = q.w();
        msg.pose.orientation.x = q.x();
        msg.pose.orientation.y = q.y();
        msg.pose.orientation.z = q.z();

        pose_pub_->publish(msg);
        published_any = true;
        break;  // only the first detection of the target ID is used
    }

    // TODO: optical flow — GHOST_V12 §Vision Pipeline

    if (!published_any) {
        RCLCPP_DEBUG(get_logger(), "No tag %d detected in this frame", target_tag_id_);
    }

    apriltag_detections_destroy(detections);
}

// ─────────────────────────────────────────────────────────────────────────────
// debugTimerCallback — publishes annotated mono8 frame at 5 Hz
// Not consumed by any filter — only for operator visualisation.
// ─────────────────────────────────────────────────────────────────────────────
void VisionNode::debugTimerCallback()
{
    // Copy frame data under the lock, then release the lock before calling
    // publish().  publish() can block in the DDS middleware (serialization,
    // socket write) and holding debug_mutex_ during that time stalls the
    // libcamera callback thread, draining the request queue and stopping capture.
    sensor_msgs::msg::Image msg{};
    {
        std::lock_guard<std::mutex> lock(debug_mutex_);
        if (debug_frame_.empty()) return;
        msg.height       = static_cast<uint32_t>(debug_height_);
        msg.width        = static_cast<uint32_t>(debug_width_);
        msg.encoding     = "mono8";
        msg.is_bigendian = 0;
        msg.step         = static_cast<uint32_t>(debug_width_);
        msg.data         = debug_frame_;   // vector copy under lock
    }                                      // mutex released here
    msg.header.stamp    = now();
    msg.header.frame_id = "camera_link";
    debug_pub_->publish(msg);              // no lock held during DDS write
}

}  // namespace ghost

// ─────────────────────────────────────────────────────────────────────────────
// main
// ─────────────────────────────────────────────────────────────────────────────
int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);

    // Node construction and initialize() both throw on failure (calibration guard,
    // hardware errors).  Both must be inside the try block so the catch can log
    // the error.  node is declared inside the block so get_logger() is never
    // called on an uninitialized shared_ptr.
    try {
        auto node = std::make_shared<ghost::VisionNode>();
        node->initialize();
        rclcpp::spin(node);
    } catch (const std::exception& e) {
        RCLCPP_FATAL(rclcpp::get_logger("vision_node"),
                     "vision_node: fatal error: %s", e.what());
        rclcpp::shutdown();
        return 1;
    }

    rclcpp::shutdown();
    return 0;
}
