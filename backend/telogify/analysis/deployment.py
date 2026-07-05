"""ERS deployment / clipping detection from a distance-aligned telemetry trace.

Neither FastF1 nor OpenF1 exposes battery state of charge (F1 does not broadcast it), so
deployment is INFERRED from the speed trace: within a full-throttle, no-brake run down a
straight, the point where speed stops rising and starts falling is where the car's electrical
deployment has tapered or run out (2026 MGU-K boost tapers above ~290 km/h). The distance the
car keeps running at full throttle PAST that peak, before it brakes or lifts, is the 'clip
distance' - where the car is no longer accelerating and is vulnerable to a car still deploying.

Speed FALLING (not merely plateauing) at full throttle separates real clipping from a
drag-limited top speed, and the effect differs by car on the same straight, so it is a car
characteristic, not track geometry. Pure and unit-tested offline.
"""

from dataclasses import dataclass

# calibration knobs (physical world needs tuning a minimal model can't see)
FULL_THROTTLE = 99.0  # throttle % counted as "full" (FastF1 0-100; 104 = error, treated as full)
MIN_STRAIGHT_M = 250.0  # ignore short inter-corner squirts; a real deployment straight is longer
MIN_CLIP_M = 40.0  # full-throttle distance past the speed peak to count as clipping
MIN_DROP_KMH = 2.0  # speed must actually fall this much after the peak (else it is drag-limited)


@dataclass(frozen=True)
class StraightRun:
    start_m: float
    end_m: float
    peak_kmh: float
    peak_at_m: float
    clip_m: float  # distance at full throttle after the speed peak (0 = still accelerating at the end)
    drop_kmh: float  # speed lost from peak to the end of the full-throttle run
    end_reason: str  # "brake" or "lift"
    is_clip: bool


def detect_clipping(
    distance: list[float],
    speed: list[float],
    throttle: list[float],
    brake: list[bool],
    min_straight_m: float = MIN_STRAIGHT_M,
) -> list[StraightRun]:
    """Find full-throttle, no-brake runs (straights) and, within each, where deployment tapers.
    All four lists are the same length, sampled along the lap and aligned by `distance` (m)."""
    n = len(distance)
    runs: list[StraightRun] = []
    i = 0
    while i < n:
        if throttle[i] < FULL_THROTTLE or brake[i]:
            i += 1
            continue
        j = i
        while j < n and throttle[j] >= FULL_THROTTLE and not brake[j]:
            j += 1
        d, sp = distance[i:j], speed[i:j]
        if len(sp) >= 3 and (d[-1] - d[0]) >= min_straight_m:
            pk = max(range(len(sp)), key=lambda k: sp[k])
            clip_m = d[-1] - d[pk]
            drop = sp[pk] - sp[-1]
            ended_on_brake = j < n and brake[j]
            runs.append(
                StraightRun(
                    start_m=d[0],
                    end_m=d[-1],
                    peak_kmh=sp[pk],
                    peak_at_m=d[pk],
                    clip_m=clip_m,
                    drop_kmh=drop,
                    end_reason="brake" if ended_on_brake else "lift",
                    is_clip=clip_m >= MIN_CLIP_M and drop >= MIN_DROP_KMH,
                )
            )
        i = j if j > i else i + 1
    return runs


def summarize_deployment(runs: list[StraightRun]) -> dict:
    """Per-lap deployment summary. total_clip_m and max_clip_m are cross-car comparable without
    matching individual straights (a car that clips more runs out of deployment sooner)."""
    clips = [r for r in runs if r.is_clip]
    return {
        "n_straights": len(runs),
        "n_clips": len(clips),
        "total_clip_m": round(sum(r.clip_m for r in clips), 1),
        "max_clip_m": round(max((r.clip_m for r in clips), default=0.0), 1),
        "top_speed_kmh": round(max((r.peak_kmh for r in runs), default=0.0), 1),
    }
