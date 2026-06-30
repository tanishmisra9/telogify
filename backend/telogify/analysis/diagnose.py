"""`telogify diagnose <year> <round>`: ranking-sanity report.

Prints, per constructor, clean-lap counts per corner and mean attribution confidence,
so thin-data teams and broken rankings are visible in one command.
"""

from collections import defaultdict
from statistics import mean

from sqlmodel import Session as DBSession
from sqlmodel import select

from telogify.analysis.attribution import _driver_constructor_map
from telogify.models import Attribution, Fingerprint, RaceWeekend, Session


def diagnose(year: int, round: int, db: DBSession) -> str:
    weekend = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year, RaceWeekend.round == round)
    ).first()
    if weekend is None:
        return f"No weekend found for {year} round {round}. Run `telogify run-weekend` first."

    sessions = db.exec(select(Session).where(Session.weekend_id == weekend.id)).all()
    session_ids = [s.id for s in sessions]
    dc_map = _driver_constructor_map(db, session_ids)

    fps = db.exec(select(Fingerprint).where(Fingerprint.session_id.in_(session_ids))).all()
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for fp in fps:
        constructor = dc_map.get(fp.driver)
        if constructor:
            counts[constructor][fp.corner_number] += fp.clean_lap_count

    attrs = db.exec(select(Attribution).where(Attribution.session_id.in_(session_ids))).all()
    confidences: dict[str, list[float]] = defaultdict(list)
    for a in attrs:
        if a.confidence is not None:
            confidences[a.constructor_a].append(a.confidence)
            confidences[a.constructor_b].append(a.confidence)

    lines = [f"Diagnose: {weekend.event_name} ({year} round {round})", ""]
    for constructor in sorted(counts):
        corners = counts[constructor]
        confs = confidences.get(constructor, [])
        mean_conf = f"{mean(confs):.2f}" if confs else "n/a"
        lines.append(
            f"{constructor}: corners={len(corners)} "
            f"total_clean_laps={sum(corners.values())} mean_attr_confidence={mean_conf}"
        )
        for corner in sorted(corners):
            lines.append(f"    T{corner}: clean_laps={corners[corner]}")
        lines.append("")
    return "\n".join(lines).rstrip()
