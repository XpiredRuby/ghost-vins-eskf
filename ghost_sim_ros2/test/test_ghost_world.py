import math

from ghost_sim_ros2.ghost_world import (
    CameraModel,
    GuidanceController,
    GuidanceLimits,
    ObserverState,
    RectObstacle,
    Vec2,
    WorldModel,
    astar_path,
    camera_visibility,
    default_target_trajectory,
    segment_intersects_rect,
)


def test_segment_rectangle_intersection_and_clear_miss():
    obstacle = RectObstacle("wall", -0.5, 0.5, -1.0, 1.0)
    assert segment_intersects_rect(Vec2(-2.0, 0.0), Vec2(2.0, 0.0), obstacle)
    assert segment_intersects_rect(Vec2(-2.0, 1.0), Vec2(2.0, 1.0), obstacle)
    assert not segment_intersects_rect(Vec2(-2.0, 1.2), Vec2(2.0, 1.2), obstacle)


def test_camera_visibility_distinguishes_obstacle_fov_and_range():
    world = WorldModel(obstacles=(RectObstacle("wall", -0.5, 0.5, -1.0, 1.0),))
    camera = CameraModel(range_m=5.0, fov_deg=90.0)
    blocked = camera_visibility(world, Vec2(-2.0, 0.0), 0.0, Vec2(2.0, 0.0), camera)
    assert not blocked.visible
    assert blocked.reason == "OCCLUDED_BY_OBSTACLE"
    assert blocked.blocker == "wall"

    visible = camera_visibility(world, Vec2(-2.0, 2.0), 0.0, Vec2(1.0, 2.0), camera)
    assert visible.visible
    behind = camera_visibility(world, Vec2(-2.0, 2.0), 0.0, Vec2(-3.0, 2.0), camera)
    assert behind.reason == "OUT_OF_FOV"
    far = camera_visibility(world, Vec2(-2.0, 2.0), 0.0, Vec2(4.0, 2.0), camera)
    assert far.reason == "OUT_OF_RANGE"


def test_astar_path_is_collision_free_around_center_building():
    world = WorldModel()
    start = Vec2(-3.0, 0.0)
    goal = Vec2(3.0, 0.0)
    path = astar_path(world, start, goal, clearance=0.30, resolution=0.25)
    assert len(path) >= 3
    assert path[0] == start
    assert path[-1].distance(goal) < 0.30
    assert all(world.point_clear(point, 0.30) for point in path)
    assert all(world.segment_clear(a, b, 0.30) for a, b in zip(path, path[1:]))


def test_guidance_respects_speed_acceleration_yaw_and_collision_limits():
    world = WorldModel()
    limits = GuidanceLimits(
        max_speed_mps=1.0,
        max_accel_mps2=0.5,
        max_yaw_rate_rps=0.8,
        obstacle_clearance_m=0.35,
    )
    controller = GuidanceController(world, limits)
    observer = ObserverState(Vec2(-4.0, -2.0), Vec2(0.0, 0.0), 0.0)
    output = controller.compute(observer, Vec2(-2.0, 0.0), Vec2(0.5, 0.0), True, 0.1)
    assert output.velocity_command.norm() <= 0.0500001
    assert abs(output.yaw_rate_command) <= 0.8000001
    assert all(world.segment_clear(a, b, limits.obstacle_clearance_m) for a, b in zip(output.path, output.path[1:]))

    previous = output.velocity_command
    for _ in range(30):
        output = controller.compute(observer, Vec2(3.0, 0.0), Vec2(0.5, 0.0), False, 0.1)
        assert output.velocity_command.norm() <= 1.0000001
        assert (output.velocity_command - previous).norm() <= 0.0500001
        assert abs(output.yaw_rate_command) <= 0.8000001
        previous = output.velocity_command


def test_default_target_mission_contains_turn_and_finishes():
    trajectory = default_target_trajectory(0.55)
    start = trajectory.sample(0.0)
    middle = trajectory.sample(trajectory.duration_s * 0.50)
    end = trajectory.sample(trajectory.duration_s + 1.0)
    assert start.position.distance(end.position) > 1.0
    assert middle.segment_index >= 1
    assert end.finished
    assert end.velocity.norm() == 0.0


def test_fixed_observer_sees_obstacle_occlusion_then_reappearance():
    world = WorldModel()
    trajectory = default_target_trajectory(0.55)
    observer = Vec2(-4.3, -2.3)
    camera = CameraModel(range_m=9.0, fov_deg=170.0)
    reasons = []
    for step in range(int(trajectory.duration_s * 10) + 1):
        sample = trajectory.sample(step / 10.0)
        yaw = math.atan2(sample.position.y - observer.y, sample.position.x - observer.x)
        result = camera_visibility(world, observer, yaw, sample.position, camera)
        reasons.append(result.reason)
    assert "OCCLUDED_BY_OBSTACLE" in reasons
    first = reasons.index("OCCLUDED_BY_OBSTACLE")
    assert "VISIBLE" in reasons[first + 1 :]
