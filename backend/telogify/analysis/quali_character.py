"""Qualifying car-character labels.

Labels a car's aero/drag character purely from the measured numbers, relative to the
other teams being compared (there is no absolute km/h threshold for "drag limited"; it
depends on the field that weekend). The model never supplies aero intuition: every label
here is a deterministic function of ranks within the compared set.

Rules (from the brief, applied via rank within the compared teams):
  - top speed and full-throttle time both in the faster half -> "efficient, low drag"
  - top speed in the slower half but fastest-corner speed in the faster half
    -> "draggy, high-downforce"
  - both top speed and full-throttle time in the slower half -> "lacks efficiency"
  - otherwise -> "balanced" (no strong signal either way)
  - highest minimum speed in the set, independently -> tagged "strong grip in the slow
    stuff" (this is a separate trait, not mutually exclusive with the drag label)

"Fastest corner" is picked once across the compared teams (the corner with the highest
average minimum speed), so every team's downforce is read through the same corner rather
than each team's own personal-best corner.
"""

from dataclasses import dataclass
from statistics import mean

# Car character compares the front of the field, not the whole grid: "leader" labels
# (best top speed, best downforce, ...) are computed relative to this set, so trimming
# happens before labeling, not after.
TOP_TEAMS_N = 5

DRAG_EFFICIENT = "efficient, low drag"
DRAG_HIGH_DOWNFORCE = "draggy, high-downforce"
DRAG_LACKS_EFFICIENCY = "lacks efficiency"
DRAG_BALANCED = "balanced"

# A "corner" only counts as a real cornering test if the field loses at least this much
# speed there versus their own top speed. Some numbered corners (e.g. a fast kink barely
# off full throttle) lose almost nothing and would otherwise look like "the fastest
# corner" simply because nobody brakes for them; mirrors REAL_STRAIGHT_KMH in straights.py.
MIN_CORNER_LOSS_KMH = 40.0


@dataclass
class CarCharacterRow:
    constructor: str
    driver: str
    lap_time_s: float
    top_speed_kmh: float
    min_speed_kmh: float
    full_throttle_pct: float
    fastest_corner_kmh: float | None
    drag_label: str
    is_top_speed_leader: bool
    is_corner_speed_leader: bool
    is_grip_leader: bool


def pick_fastest_corner(rows: list[dict], min_loss_kmh: float = MIN_CORNER_LOSS_KMH) -> int | None:
    """rows: dicts with `top_speed_kmh` and a `corner_speeds` map (corner_number ->
    min_speed_kmh) for one representative lap per team. The fastest corner is the one
    with the highest average speed across these teams, among corners where the field
    actually loses meaningful speed (excludes kinks taken at near-top-speed, which would
    otherwise "win" trivially).
    """
    by_corner: dict[int, list[float]] = {}
    for r in rows:
        top = r.get("top_speed_kmh")
        for corner, speed in (r.get("corner_speeds") or {}).items():
            if top is not None and (top - speed) < min_loss_kmh:
                continue
            by_corner.setdefault(corner, []).append(speed)
    if not by_corner:
        return None
    return max(by_corner, key=lambda c: mean(by_corner[c]))


def _rank_desc(values: list[float]) -> list[int]:
    """1 = highest value. Ties share the lower (better) rank."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    ranks = [0] * len(values)
    for position, idx in enumerate(order):
        ranks[idx] = position + 1
    return ranks


def label_car_character(rows: list[dict]) -> list[CarCharacterRow]:
    """rows: dicts with constructor, driver, lap_time_s, top_speed_kmh, min_speed_kmh,
    full_throttle_pct, corner_speeds (corner_number -> min_speed_kmh for this lap).

    One row per constructor is expected (pick each team's fastest qualifier upstream).
    """
    if not rows:
        return []
    n = len(rows)
    half = -(-n // 2)  # ceil(n/2): ranks 1..half count as "faster half"

    fastest_corner = pick_fastest_corner(rows)
    corner_speed = [
        (r.get("corner_speeds") or {}).get(fastest_corner) if fastest_corner is not None else None
        for r in rows
    ]

    speed_ranks = _rank_desc([r["top_speed_kmh"] for r in rows])
    throttle_ranks = _rank_desc([r["full_throttle_pct"] for r in rows])
    corner_ranks = _rank_desc([c if c is not None else float("-inf") for c in corner_speed])
    grip_ranks = _rank_desc([r["min_speed_kmh"] for r in rows])

    out = []
    for i, r in enumerate(rows):
        fast_top_speed = speed_ranks[i] <= half
        fast_throttle = throttle_ranks[i] <= half
        fast_corner = corner_ranks[i] <= half

        if fast_top_speed and fast_throttle:
            label = DRAG_EFFICIENT
        elif not fast_top_speed and fast_corner:
            label = DRAG_HIGH_DOWNFORCE
        elif not fast_top_speed and not fast_throttle:
            label = DRAG_LACKS_EFFICIENCY
        else:
            label = DRAG_BALANCED

        out.append(
            CarCharacterRow(
                constructor=r["constructor"],
                driver=r["driver"],
                lap_time_s=r["lap_time_s"],
                top_speed_kmh=r["top_speed_kmh"],
                min_speed_kmh=r["min_speed_kmh"],
                full_throttle_pct=r["full_throttle_pct"],
                fastest_corner_kmh=corner_speed[i],
                drag_label=label,
                is_top_speed_leader=speed_ranks[i] == 1,
                is_corner_speed_leader=corner_ranks[i] == 1,
                is_grip_leader=grip_ranks[i] == 1,
            )
        )
    return out


def fastest_qualifier_per_constructor(rows: list[dict]) -> list[dict]:
    """rows: dicts with constructor, lap_time_s, ... . Collapses to one row per constructor:
    that team's fastest qualifier, since the car-character table compares teams, not drivers.
    """
    best: dict[str, dict] = {}
    for r in rows:
        constructor = r.get("constructor")
        if constructor is None:
            continue
        if constructor not in best or r["lap_time_s"] < best[constructor]["lap_time_s"]:
            best[constructor] = r
    return sorted(best.values(), key=lambda r: r["lap_time_s"])
