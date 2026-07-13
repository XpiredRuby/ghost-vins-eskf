"""Deterministic planar world, visibility, path-planning, and guidance utilities.

The coordinate frame is a local mission frame anchored at simulation start.  It is
not a GPS frame.  Target measurements are emitted only when the simulated camera
has line of sight, range, and field-of-view access to the target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math
from typing import Iterable, Sequence


EPS = 1.0e-9


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def norm(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self, fallback: "Vec2" | None = None) -> "Vec2":
        n = self.norm()
        if n <= EPS:
            return fallback if fallback is not None else Vec2(1.0, 0.0)
        return Vec2(self.x / n, self.y / n)

    def distance(self, other: "Vec2") -> float:
        return (self - other).norm()

    def as_list(self) -> list[float]:
        return [float(self.x), float(self.y)]


@dataclass(frozen=True)
class RectObstacle:
    name: str
    xmin: float
    xmax: float
    ymin: float
    ymax: float

    def __post_init__(self) -> None:
        if self.xmin >= self.xmax or self.ymin >= self.ymax:
            raise ValueError(f"invalid obstacle bounds for {self.name}")

    def contains(self, p: Vec2, margin: float = 0.0) -> bool:
        return (
            self.xmin - margin <= p.x <= self.xmax + margin
            and self.ymin - margin <= p.y <= self.ymax + margin
        )

    def expanded(self, margin: float) -> "RectObstacle":
        return RectObstacle(
            self.name,
            self.xmin - margin,
            self.xmax + margin,
            self.ymin - margin,
            self.ymax + margin,
        )

    def corners(self, margin: float = 0.0) -> tuple[Vec2, Vec2, Vec2, Vec2]:
        r = self.expanded(margin)
        return (
            Vec2(r.xmin, r.ymin),
            Vec2(r.xmin, r.ymax),
            Vec2(r.xmax, r.ymin),
            Vec2(r.xmax, r.ymax),
        )

    def to_dict(self) -> dict[str, float | str]:
        return {
            "name": self.name,
            "xmin": self.xmin,
            "xmax": self.xmax,
            "ymin": self.ymin,
            "ymax": self.ymax,
        }


@dataclass(frozen=True)
class WorldModel:
    xmin: float = -6.0
    xmax: float = 6.0
    ymin: float = -4.0
    ymax: float = 4.0
    obstacles: tuple[RectObstacle, ...] = field(
        default_factory=lambda: (
            RectObstacle("center_building", -0.65, 0.65, -1.55, 1.55),
            RectObstacle("north_block", 2.15, 3.15, 1.35, 2.65),
        )
    )

    def inside_bounds(self, p: Vec2, margin: float = 0.0) -> bool:
        return (
            self.xmin + margin <= p.x <= self.xmax - margin
            and self.ymin + margin <= p.y <= self.ymax - margin
        )

    def point_clear(self, p: Vec2, clearance: float = 0.0) -> bool:
        if not self.inside_bounds(p, clearance):
            return False
        return not any(ob.contains(p, clearance) for ob in self.obstacles)

    def segment_clear(self, a: Vec2, b: Vec2, clearance: float = 0.0) -> bool:
        if not self.point_clear(a, clearance) or not self.point_clear(b, clearance):
            return False
        return not any(segment_intersects_rect(a, b, ob.expanded(clearance)) for ob in self.obstacles)

    def first_blocker(self, a: Vec2, b: Vec2, clearance: float = 0.0) -> RectObstacle | None:
        for ob in self.obstacles:
            if segment_intersects_rect(a, b, ob.expanded(clearance)):
                return ob
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "bounds": [self.xmin, self.xmax, self.ymin, self.ymax],
            "obstacles": [ob.to_dict() for ob in self.obstacles],
        }


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def angle_to(a: Vec2, b: Vec2) -> float:
    return math.atan2(b.y - a.y, b.x - a.x)


def segment_intersects_rect(a: Vec2, b: Vec2, rect: RectObstacle) -> bool:
    """Return True when closed segment AB intersects an axis-aligned rectangle.

    Liang-Barsky clipping is used so corner touches count as blocked line of sight.
    """

    dx = b.x - a.x
    dy = b.y - a.y
    p = (-dx, dx, -dy, dy)
    q = (a.x - rect.xmin, rect.xmax - a.x, a.y - rect.ymin, rect.ymax - a.y)
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) <= EPS:
            if qi < 0.0:
                return False
            continue
        t = qi / pi
        if pi < 0.0:
            u1 = max(u1, t)
        else:
            u2 = min(u2, t)
        if u1 - u2 > EPS:
            return False
    return True


@dataclass(frozen=True)
class CameraModel:
    range_m: float = 8.0
    fov_deg: float = 118.0


@dataclass(frozen=True)
class VisibilityResult:
    visible: bool
    reason: str
    distance_m: float
    bearing_error_rad: float
    blocker: str | None = None


def camera_visibility(
    world: WorldModel,
    observer: Vec2,
    observer_yaw: float,
    target: Vec2,
    camera: CameraModel,
) -> VisibilityResult:
    delta = target - observer
    distance = delta.norm()
    bearing_error = wrap_angle(math.atan2(delta.y, delta.x) - observer_yaw)
    if distance > camera.range_m:
        return VisibilityResult(False, "OUT_OF_RANGE", distance, bearing_error)
    if abs(bearing_error) > math.radians(camera.fov_deg) * 0.5:
        return VisibilityResult(False, "OUT_OF_FOV", distance, bearing_error)
    blocker = world.first_blocker(observer, target)
    if blocker is not None:
        return VisibilityResult(False, "OCCLUDED_BY_OBSTACLE", distance, bearing_error, blocker.name)
    return VisibilityResult(True, "VISIBLE", distance, bearing_error)


@dataclass(frozen=True)
class TrajectorySample:
    position: Vec2
    velocity: Vec2
    finished: bool
    segment_index: int


class PolylineTrajectory:
    def __init__(self, waypoints: Sequence[Vec2], speed_mps: float, hold_last: bool = True) -> None:
        if len(waypoints) < 2:
            raise ValueError("trajectory requires at least two waypoints")
        if speed_mps <= 0.0:
            raise ValueError("speed_mps must be positive")
        self.waypoints = tuple(waypoints)
        self.speed_mps = float(speed_mps)
        self.hold_last = bool(hold_last)
        self.lengths = [a.distance(b) for a, b in zip(self.waypoints, self.waypoints[1:])]
        self.cumulative = [0.0]
        for length in self.lengths:
            self.cumulative.append(self.cumulative[-1] + length)
        self.total_length = self.cumulative[-1]
        self.duration_s = self.total_length / self.speed_mps

    def sample(self, t_s: float) -> TrajectorySample:
        distance = max(0.0, t_s) * self.speed_mps
        finished = distance >= self.total_length
        if finished and self.hold_last:
            return TrajectorySample(self.waypoints[-1], Vec2(0.0, 0.0), True, len(self.lengths) - 1)
        if self.total_length <= EPS:
            return TrajectorySample(self.waypoints[-1], Vec2(0.0, 0.0), True, 0)
        distance = distance % self.total_length
        index = len(self.lengths) - 1
        for i, end in enumerate(self.cumulative[1:]):
            if distance <= end + EPS:
                index = i
                break
        start = self.waypoints[index]
        end = self.waypoints[index + 1]
        length = max(self.lengths[index], EPS)
        local = clamp((distance - self.cumulative[index]) / length, 0.0, 1.0)
        direction = (end - start).normalized()
        return TrajectorySample(
            start + (end - start) * local,
            direction * self.speed_mps,
            finished,
            index,
        )


def default_target_trajectory(speed_mps: float = 0.55) -> PolylineTrajectory:
    """Target crosses behind the center building, turns a corner, then exits north-west."""

    return PolylineTrajectory(
        (
            Vec2(-4.1, -0.55),
            Vec2(-1.25, -0.55),
            Vec2(1.35, -0.55),
            Vec2(1.55, 1.05),
            Vec2(1.55, 2.75),
            Vec2(-3.75, 2.75),
        ),
        speed_mps=speed_mps,
        hold_last=True,
    )


@dataclass
class ObserverState:
    position: Vec2
    velocity: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    yaw: float = 0.0


@dataclass(frozen=True)
class GuidanceLimits:
    max_speed_mps: float = 1.15
    max_accel_mps2: float = 1.4
    max_yaw_rate_rps: float = 1.5
    standoff_m: float = 2.2
    obstacle_clearance_m: float = 0.38
    goal_tolerance_m: float = 0.20
    grid_resolution_m: float = 0.25


@dataclass(frozen=True)
class GuidanceOutput:
    velocity_command: Vec2
    yaw_rate_command: float
    final_goal: Vec2
    active_waypoint: Vec2
    path: tuple[Vec2, ...]
    mode: str


def desired_standoff_position(observer: Vec2, target: Vec2, target_velocity: Vec2, standoff_m: float) -> Vec2:
    if target_velocity.norm() > 0.08:
        offset_dir = target_velocity.normalized() * -1.0
    else:
        offset_dir = (observer - target).normalized(Vec2(-1.0, 0.0))
    return target + offset_dir * standoff_m


def candidate_vantage_points(obstacle: RectObstacle, clearance: float) -> tuple[Vec2, ...]:
    pad = clearance + 0.30
    return obstacle.corners(pad)


def choose_vantage_goal(
    world: WorldModel,
    observer: Vec2,
    target_estimate: Vec2,
    clearance: float,
    blocking_obstacle_name: str | None = None,
) -> Vec2:
    blocker = None
    if blocking_obstacle_name:
        blocker = next((ob for ob in world.obstacles if ob.name == blocking_obstacle_name), None)
    if blocker is None:
        blocker = world.first_blocker(observer, target_estimate)
    candidates: list[Vec2] = []
    if blocker is not None:
        candidates.extend(candidate_vantage_points(blocker, clearance))
    else:
        for obstacle in world.obstacles:
            if obstacle.contains(target_estimate, 1.0):
                candidates.extend(candidate_vantage_points(obstacle, clearance))
    valid = [
        p
        for p in candidates
        if world.point_clear(p, clearance)
        and world.first_blocker(p, target_estimate) is None
    ]
    if not valid:
        # Search a ring around the estimate for any clear line-of-sight vantage.
        for radius in (2.0, 2.6, 3.2):
            for k in range(16):
                theta = 2.0 * math.pi * k / 16.0
                p = target_estimate + Vec2(math.cos(theta), math.sin(theta)) * radius
                if world.point_clear(p, clearance) and world.first_blocker(p, target_estimate) is None:
                    valid.append(p)
    if not valid:
        return observer
    return min(valid, key=lambda p: observer.distance(p) + 0.20 * p.distance(target_estimate))


def astar_path(
    world: WorldModel,
    start: Vec2,
    goal: Vec2,
    clearance: float,
    resolution: float = 0.25,
) -> tuple[Vec2, ...]:
    """Plan a collision-free 8-connected grid path and simplify visible segments."""

    resolution = max(0.10, float(resolution))

    def to_index(p: Vec2) -> tuple[int, int]:
        return (
            int(round((p.x - world.xmin) / resolution)),
            int(round((p.y - world.ymin) / resolution)),
        )

    def to_point(idx: tuple[int, int]) -> Vec2:
        return Vec2(world.xmin + idx[0] * resolution, world.ymin + idx[1] * resolution)

    start_idx = to_index(start)
    goal_idx = to_index(goal)
    if not world.point_clear(goal, clearance):
        goal = nearest_clear_point(world, goal, clearance, resolution)
        goal_idx = to_index(goal)
    if world.segment_clear(start, goal, clearance):
        return (start, goal)

    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (0.0, counter, start_idx))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score = {start_idx: 0.0}
    closed: set[tuple[int, int]] = set()
    moves = (
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, math.sqrt(2.0)),
        (-1, 1, math.sqrt(2.0)),
        (1, -1, math.sqrt(2.0)),
        (1, 1, math.sqrt(2.0)),
    )

    def heuristic(idx: tuple[int, int]) -> float:
        return math.hypot(idx[0] - goal_idx[0], idx[1] - goal_idx[1])

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal_idx:
            break
        closed.add(current)
        current_point = to_point(current)
        for dx, dy, cost in moves:
            neighbor = (current[0] + dx, current[1] + dy)
            point = to_point(neighbor)
            if not world.point_clear(point, clearance):
                continue
            if not world.segment_clear(current_point, point, clearance):
                continue
            tentative = g_score[current] + cost
            if tentative + EPS >= g_score.get(neighbor, math.inf):
                continue
            came_from[neighbor] = current
            g_score[neighbor] = tentative
            counter += 1
            heapq.heappush(open_heap, (tentative + heuristic(neighbor), counter, neighbor))

    if goal_idx not in came_from:
        return (start,)
    indices = [goal_idx]
    while indices[-1] != start_idx:
        indices.append(came_from[indices[-1]])
    indices.reverse()
    raw = [start] + [to_point(idx) for idx in indices[1:-1]] + [goal]
    return simplify_path(world, raw, clearance)


def simplify_path(world: WorldModel, points: Sequence[Vec2], clearance: float) -> tuple[Vec2, ...]:
    if len(points) <= 2:
        return tuple(points)
    simplified = [points[0]]
    anchor = 0
    while anchor < len(points) - 1:
        farthest = anchor + 1
        for candidate in range(anchor + 2, len(points)):
            if world.segment_clear(points[anchor], points[candidate], clearance):
                farthest = candidate
            else:
                break
        simplified.append(points[farthest])
        anchor = farthest
    return tuple(simplified)


def nearest_clear_point(world: WorldModel, point: Vec2, clearance: float, step: float = 0.25) -> Vec2:
    if world.point_clear(point, clearance):
        return point
    for ring in range(1, 30):
        radius = ring * step
        for k in range(max(8, ring * 8)):
            theta = 2.0 * math.pi * k / max(8, ring * 8)
            candidate = point + Vec2(math.cos(theta), math.sin(theta)) * radius
            if world.point_clear(candidate, clearance):
                return candidate
    return point


class GuidanceController:
    def __init__(self, world: WorldModel, limits: GuidanceLimits | None = None) -> None:
        self.world = world
        self.limits = limits or GuidanceLimits()
        self.previous_command = Vec2(0.0, 0.0)

    def compute(
        self,
        observer: ObserverState,
        target_estimate: Vec2,
        target_velocity: Vec2,
        visible: bool,
        dt_s: float,
        blocking_obstacle_name: str | None = None,
    ) -> GuidanceOutput:
        limits = self.limits
        if visible:
            mode = "VISIBLE_STANDOFF_TRACK"
            goal = desired_standoff_position(
                observer.position,
                target_estimate,
                target_velocity,
                limits.standoff_m,
            )
            goal = nearest_clear_point(self.world, goal, limits.obstacle_clearance_m)
        else:
            mode = "HIDDEN_VANTAGE_REPOSITION"
            goal = choose_vantage_goal(
                self.world,
                observer.position,
                target_estimate,
                limits.obstacle_clearance_m,
                blocking_obstacle_name,
            )
        path = astar_path(
            self.world,
            observer.position,
            goal,
            limits.obstacle_clearance_m,
            limits.grid_resolution_m,
        )
        waypoint = path[1] if len(path) > 1 else observer.position
        delta = waypoint - observer.position
        if delta.norm() <= limits.goal_tolerance_m and len(path) > 2:
            waypoint = path[2]
            delta = waypoint - observer.position
        desired = delta.normalized(Vec2(0.0, 0.0)) * limits.max_speed_mps
        if observer.position.distance(goal) <= limits.goal_tolerance_m:
            desired = Vec2(0.0, 0.0)
        max_delta = limits.max_accel_mps2 * max(dt_s, 1.0e-3)
        command_delta = desired - self.previous_command
        if command_delta.norm() > max_delta:
            command_delta = command_delta.normalized() * max_delta
        command = self.previous_command + command_delta
        if command.norm() > limits.max_speed_mps:
            command = command.normalized() * limits.max_speed_mps
        self.previous_command = command
        desired_yaw = angle_to(observer.position, target_estimate)
        yaw_error = wrap_angle(desired_yaw - observer.yaw)
        yaw_rate = clamp(yaw_error / max(dt_s, 0.05), -limits.max_yaw_rate_rps, limits.max_yaw_rate_rps)
        return GuidanceOutput(command, yaw_rate, goal, waypoint, path, mode)


def path_length(points: Iterable[Vec2]) -> float:
    pts = list(points)
    return sum(a.distance(b) for a, b in zip(pts, pts[1:]))
