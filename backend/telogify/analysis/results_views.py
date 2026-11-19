"""Pure shaping for the qualifying segment ladder and the race results graphic (no DB, no FastF1).

Qualifying: every runner appears in each segment they ENTERED, with their time in that segment, as on
the printed ladders. Who entered a segment comes from the classified POSITION, never from which times
exist: a car can reach Q2 and set no Q2 time, and a Q3 time can be slower than the same car's Q2.
Checked against all 2026 Q/SQ sessions in the dev DB: no Q3 time outside P1-10, no Q2 time outside
P1-16, null-position cars are Q1 no-times. The 20-car split (P1-15 into Q2) is assumed, not checked.
"""

Q3_SIZE = 10
CLASSIFIED_STATUSES = ("finished", "lapped")


def segment_sizes(field_size: int) -> tuple[int, int]:
    """(cars entering Q2, cars entering Q3) for a field. 22 cars lose 6 in Q1, a 20-car field loses 5.
    Clamped so a tiny test field never yields a negative or inverted split."""
    q3 = min(Q3_SIZE, field_size)
    q1_out = 6 if field_size >= 22 else 5
    q2 = max(q3, field_size - q1_out)
    return q2, q3


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 3)


def build_quali_segments(rows: list[dict], session_type: str) -> dict:
    """rows: {driver, constructor, position|None, q1_s, q2_s, q3_s}. Returns segments top band first
    (Q3, Q2, Q1). `cut_s` is the slowest time among the cars that advanced (None for the last
    segment, or when none of them has a time); `gap_to_cut_s` is negative for a car through. Empty
    `segments` when no row carries any segment time, so a caller can hide the graphic."""
    if not any(r.get(k) is not None for r in rows for k in ("q1_s", "q2_s", "q3_s")):
        return {"session_type": session_type, "segments": []}

    q2_size, q3_size = segment_sizes(len(rows))
    prefix = "SQ" if session_type == "SQ" else "Q"
    # (number, key, entered(position), advanced(position) or None for the final segment)
    plan = [
        (3, "q3_s", lambda p: p is not None and p <= q3_size, None),
        (2, "q2_s", lambda p: p is not None and p <= q2_size, lambda p: p is not None and p <= q3_size),
        (1, "q1_s", lambda p: True, lambda p: p is not None and p <= q2_size),
    ]
    segments = []
    for number, key, entered, advanced in plan:
        members = [r for r in rows if entered(r.get("position"))]
        timed = [r[key] for r in members if r.get(key) is not None]
        fastest = min(timed) if timed else None
        adv_times = [r[key] for r in members if advanced and advanced(r.get("position")) and r.get(key) is not None]
        cut = max(adv_times) if adv_times else None
        out = []
        for r in sorted(members, key=lambda r: (r.get(key) is None, r.get(key) or 0.0, r.get("position") is None, r.get("position") or 0)):
            t = r.get(key)
            out.append({
                "driver": r["driver"],
                "constructor": r.get("constructor"),
                "position": r.get("position"),
                "time_s": _r(t),
                "gap_to_fastest_s": None if t is None or fastest is None else _r(t - fastest),
                "gap_to_cut_s": None if t is None or cut is None else _r(t - cut),
                "advanced": None if advanced is None else bool(advanced(r.get("position"))),
            })
        segments.append({"name": f"{prefix}{number}", "fastest_s": _r(fastest), "cut_s": _r(cut), "rows": out})
    return {"session_type": session_type, "segments": segments}


def places_gained(grid: int | None, position: int | None, status: str | None) -> int | None:
    """Positive = gained. Only a classified finisher (status Finished or Lapped) has a number: a retiree's or DNS's
    slot is not a place they drove to, and a blank status (degraded position-only results) is unknown, never guessed.
    `grid` is the starting slot the API chose for the whole race: the official grid when every starter has one (so
    penalties are reflected), else the classified qualifying position (they are not). A pit-lane start arrives as None,
    since it is not a slot, and so does a car with no start at all."""
    if grid is None or position is None:
        return None
    if (status or "").strip().lower() not in CLASSIFIED_STATUSES:
        return None
    return grid - position
