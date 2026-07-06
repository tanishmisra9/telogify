#!/usr/bin/env python3
"""Audit persisted insights against ingested telemetry. Read-only report to stdout."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from sqlmodel import Session, select

from telogify.analysis.degradation import fit_group, REFERENCE_AGE_LAPS
from telogify.db import engine
from telogify.models import (
    ConstructorIndex,
    DeploymentTrace,
    Insight,
    RaceControlEvent,
    RaceWeekend,
    SectorBest,
    Session as SessionRow,
    SessionResult,
    Stint,
)

YEAR = 2026
TOL_PACE = 0.02  # seconds per lap rounding slack
TOL_GAP = 0.15
TOL_SPEED = 0.6
TOL_CLIP = 2.0
TOL_STINT = 0.15


@dataclass
class Finding:
    slot: int
    severity: str  # OK | WARN | FAIL
    claim: str
    detail: str


@dataclass
class RoundReport:
    round: int
    event: str
    findings: list[Finding] = field(default_factory=list)


def _sid(db: Session, wid: int, stype: str) -> int | None:
    row = db.exec(
        select(SessionRow).where(SessionRow.weekend_id == wid, SessionRow.session_type == stype)
    ).first()
    return row.id if row else None


def _results(db: Session, sid: int | None) -> list[SessionResult]:
    if sid is None:
        return []
    return list(
        db.exec(select(SessionResult).where(SessionResult.session_id == sid).order_by(SessionResult.position)).all()
    )


def _pace_index(db: Session, wid: int) -> list[ConstructorIndex]:
    return list(
        db.exec(
            select(ConstructorIndex)
            .where(ConstructorIndex.weekend_id == wid)
            .order_by(ConstructorIndex.overall_rank)
        ).all()
    )


def _deploy(db: Session, sid: int | None) -> list[DeploymentTrace]:
    if sid is None:
        return []
    return list(db.exec(select(DeploymentTrace).where(DeploymentTrace.session_id == sid)).all())


def _rc(db: Session, sid: int | None, driver: str | None = None) -> list[RaceControlEvent]:
    if sid is None:
        return []
    q = select(RaceControlEvent).where(RaceControlEvent.session_id == sid)
    if driver:
        q = q.where(RaceControlEvent.driver == driver)
    return list(db.exec(q.order_by(RaceControlEvent.lap)).all())


def _stints(db: Session, sid: int | None, driver: str | None = None) -> list[Stint]:
    if sid is None:
        return []
    q = select(Stint).where(Stint.session_id == sid)
    if driver:
        q = q.where(Stint.driver == driver)
    return list(db.exec(q.order_by(Stint.stint_number)).all())


def _sectors(db: Session, sid: int | None) -> list[SectorBest]:
    if sid is None:
        return []
    return list(db.exec(select(SectorBest).where(SectorBest.session_id == sid)).all())


def _rank_name(rows: list[ConstructorIndex], rank: int) -> str | None:
    for r in rows:
        if r.overall_rank == rank:
            return r.constructor
    return None


def _gap(db: Session, wid: int, constructor: str) -> float | None:
    for r in _pace_index(db, wid):
        if r.constructor == constructor:
            return r.lap_deficit_s
    return None


def _closest_constructor(rows: list[ConstructorIndex], gap: float) -> tuple[str, float] | None:
    best = None
    for r in rows:
        if r.lap_deficit_s is None:
            continue
        d = abs(r.lap_deficit_s - gap)
        if best is None or d < best[0]:
            best = (d, r.constructor, r.lap_deficit_s)
    if best is None:
        return None
    return best[1], best[2]


def _deg_slope(db: Session, sid: int, constructor: str, compound: str) -> float | None:
    from telogify.analysis.attribution import _driver_constructor_map

    stints = _stints(db, sid)
    dc = _driver_constructor_map(db, [sid])
    ages: list[float] = []
    times: list[float] = []
    for st in stints:
        if dc.get(st.driver) != constructor or (st.compound or "").upper() != compound.upper():
            continue
        if not st.lap_times_json or not st.tyre_ages_json:
            continue
        for age, t in zip(st.tyre_ages_json, st.lap_times_json, strict=False):
            if age is not None and t is not None:
                ages.append(float(age))
                times.append(float(t))
    if len(ages) < 5:
        return None
    fit = fit_group(constructor, compound, ages, times)
    return fit.slope_s_per_lap if fit else None


def _add(rep: RoundReport, slot: int, severity: str, claim: str, detail: str) -> None:
    rep.findings.append(Finding(slot, severity, claim, detail))


def audit_round(db: Session, w: RaceWeekend, insights: list[Insight]) -> RoundReport:
    rep = RoundReport(w.round, w.event_name)
    wid = w.id
    r_id = _sid(db, wid, "R")
    q_id = _sid(db, wid, "Q")
    sq_id = _sid(db, wid, "SQ")
    sprint_id = _sid(db, wid, "SPRINT")
    pace = _pace_index(db, wid)
    race_res = _results(db, r_id)
    quali_res = _results(db, q_id)
    q_dep = _deploy(db, q_id)
    sq_dep = _deploy(db, sq_id)

    def pos(session_results: list[SessionResult], driver: str) -> int | None:
        for r in session_results:
            if r.driver == driver:
                return r.position
        return None

    def gap(session_results: list[SessionResult], driver: str) -> float | None:
        for r in session_results:
            if r.driver == driver:
                return r.gap_to_leader
        return None

    def clip(driver: str, dep: list[DeploymentTrace]) -> float | None:
        for d in dep:
            if d.driver == driver:
                return d.total_clip_m
        return None

    def top_speed(driver: str, dep: list[DeploymentTrace]) -> float | None:
        for d in dep:
            if d.driver == driver:
                return d.top_speed_kmh
        return None

    def max_clip_driver(dep: list[DeploymentTrace]) -> tuple[str, float] | None:
        if not dep:
            return None
        best = max(dep, key=lambda d: d.total_clip_m)
        return best.driver, best.total_clip_m

    def min_clip_driver(dep: list[DeploymentTrace]) -> tuple[str, float] | None:
        if not dep:
            return None
        best = min(dep, key=lambda d: d.total_clip_m)
        return best.driver, best.total_clip_m

    for ins in insights:
        slot = ins.slot
        text = f"{ins.header} {ins.explanation_web}"
        header = ins.header
        body = ins.explanation_web

        # --- Extract cited pace gaps from prose ---
        for m in re.finditer(
            r"([\w\s]+?)(?:'s|’s)?\s+(?:median )?race pace was |"
            r"([\w\s]+?) ranked (?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+)",
            body,
            re.I,
        ):
            pass  # handled per-round below

        # Pace gap numbers: "X seconds a lap off", "Xs per lap off", "0.105 seconds a lap off"
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:s(?:ec(?:ond)?s?)?)?\s*(?:a lap |per lap )?off", body, re.I):
            cited = float(m.group(1))
            # find nearest constructor gap in DB
            match = _closest_constructor(pace, cited)
            if match is None:
                _add(rep, slot, "WARN", f"Pace gap {cited}s cited", "No constructor pace data")
            else:
                name, actual = match
                if abs(actual - cited) > TOL_PACE:
                    _add(
                        rep,
                        slot,
                        "FAIL" if abs(actual - cited) > 0.1 else "WARN",
                        f"Pace gap {cited}s",
                        f"Nearest DB: {name} {actual:.3f}s/lap (Δ {actual - cited:+.3f})",
                    )
                else:
                    _add(rep, slot, "OK", f"Pace gap {cited}s", f"Matches {name} ({actual:.3f})")

        # Rank claims: "third-fastest race pace", "ranked fifth"
        ord_map = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "sixth": 6,
            "seventh": 7,
            "eighth": 8,
            "ninth": 9,
            "tenth": 10,
            "eleventh": 11,
        }
        for word, rank in ord_map.items():
            if re.search(rf"\b{word}[- ]?(?:fastest|quickest|ranked|of)", body, re.I) or re.search(
                rf"ranked {word}\b", body, re.I
            ):
                # try to infer constructor from header/body - skip generic audit
                pass

        # Top speeds in prose
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*km/h", body):
            cited = float(m.group(1))
            hits = [
                (d.driver, d.top_speed_kmh)
                for d in q_dep + sq_dep
                if d.top_speed_kmh and abs(d.top_speed_kmh - cited) <= TOL_SPEED
            ]
            if not hits:
                _add(rep, slot, "FAIL", f"Top speed {cited} km/h", "No Q/SQ deployment trace within tolerance")
            else:
                _add(rep, slot, "OK", f"Top speed {cited} km/h", f"Found: {', '.join(f'{d} {v}' for d,v in hits[:3])}")

        # Clip distances
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:m|metres|meters)\b", body, re.I):
            cited = float(m.group(1))
            if cited < 50:  # skip lap counts etc
                continue
            hits = [
                (d.driver, d.total_clip_m)
                for d in q_dep + sq_dep
                if abs(d.total_clip_m - cited) <= TOL_CLIP
            ]
            if hits:
                _add(rep, slot, "OK", f"Clip {cited}m", f"Found: {', '.join(f'{d} {v}' for d,v in hits[:3])}")
            elif cited >= 100:
                _add(rep, slot, "WARN", f"Clip {cited}m", "No exact deployment total_clip_m match")

        # Finish gaps to winner
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*seconds? behind", body, re.I):
            cited = float(m.group(1))
            hits = [
                (r.driver, r.gap_to_leader)
                for r in race_res
                if r.gap_to_leader and abs(r.gap_to_leader - cited) <= TOL_GAP
            ]
            if hits:
                _add(rep, slot, "OK", f"Gap {cited}s to leader", f"{hits[0][0]} gap={hits[0][1]}")
            else:
                _add(rep, slot, "WARN", f"Gap {cited}s to leader", "No race result gap match")

    # --- Round-specific deep checks (headline claims) ---
    r = w.round

    if r == 1:
        ins = insights[0]
        if pos(race_res, "BEA") != 7:
            _add(rep, 1, "FAIL", "Bearman P7", f"Actual P{pos(race_res, 'BEA')}")
        haas_gap = _gap(db, wid, "Haas")
        if haas_gap and abs(haas_gap - 1.778) > TOL_PACE:
            _add(rep, 1, "FAIL", "Haas pace 1.778s", f"DB {haas_gap:.3f}")
        fer_gap = _gap(db, wid, "Ferrari")
        if fer_gap and abs(fer_gap - 0.105) > TOL_PACE:
            _add(rep, 2, "FAIL", "Ferrari 0.105s off Mercedes", f"DB {fer_gap:.3f}")
        lec_gap = gap(race_res, "LEC")
        if lec_gap and abs(lec_gap - 15.519) > TOL_GAP:
            _add(rep, 2, "WARN", "Leclerc +15.519s", f"DB {lec_gap}")
        bea_q = top_speed("BEA", q_dep)
        ham_q = top_speed("HAM", q_dep)
        if bea_q and ham_q and abs((bea_q - ham_q) - 8.6) > 2:
            _add(rep, 3, "WARN", "~7-9 km/h Haas vs Ferrari Q", f"BEA {bea_q} HAM {ham_q} Δ {bea_q-ham_q:.1f}")

    if r == 2:
        lec_c, ham_c = clip("LEC", q_dep), clip("HAM", q_dep)
        if lec_c and ham_c:
            mx = max(d.total_clip_m for d in q_dep)
            if lec_c < mx - 1 and ham_c < mx - 1:
                _add(rep, 1, "FAIL", "Ferrari deepest Q clip", f"LEC {lec_c} HAM {ham_c} max field {mx}")
        alp_rank = next((x.overall_rank for x in pace if x.constructor == "Alpine"), None)
        if alp_rank != 3:
            _add(rep, 2, "FAIL", "Alpine 3rd race pace", f"Rank {alp_rank}")
        rc_ver = [e for e in _rc(db, r_id, "VER") if e.lap == 19]
        if not rc_ver:
            _add(rep, 3, "FAIL", "VER lap-19 RC event", "Not in race_control_event")

    if r == 3:
        ant_c = clip("ANT", q_dep)
        if ant_c is None or ant_c > 200:
            _add(rep, 1, "FAIL", "Antonelli lowest Q clip ~172m", f"DB {ant_c}")
        sai_ts = top_speed("SAI", q_dep)
        field_max = max((d.top_speed_kmh or 0) for d in q_dep) if q_dep else 0
        if sai_ts and abs(sai_ts - field_max) > 0.5:
            _add(rep, 2, "FAIL", "Sainz highest Q top speed", f"SAI {sai_ts} field max {field_max}")
        pia_c, nor_c = clip("PIA", q_dep), clip("NOR", q_dep)
        if pia_c and max(d.total_clip_m for d in q_dep) > pia_c + 1:
            _add(rep, 3, "FAIL", "Piastri max Q clip", f"PIA {pia_c} not max")

    if r == 4:
        ant_c = clip("ANT", q_dep)
        mn = min_clip_driver(q_dep)
        if ant_c and mn and mn[0] != "ANT":
            _add(rep, 1, "FAIL", "Antonelli lowest Q clip", f"Min is {mn[0]} {mn[1]}m, ANT {ant_c}m")
        mcl_gap = _gap(db, wid, "McLaren")
        if mcl_gap and abs(mcl_gap - 0.081) > 0.02:
            _add(rep, 2, "FAIL", "McLaren +0.081s pace", f"DB {mcl_gap:.3f}")
        ham_rc = [e for e in _rc(db, r_id, "HAM") if e.lap == 3]
        lec_rc = [e for e in _rc(db, r_id, "LEC") if e.lap == 57]
        if not ham_rc:
            _add(rep, 3, "WARN", "HAM lap-3 collision RC", "No event")
        if not lec_rc:
            _add(rep, 3, "WARN", "LEC lap-57 collision RC", "No event")

    if r == 5:
        mcl_gap = _gap(db, wid, "McLaren")
        if mcl_gap and abs(mcl_gap - 0.795) > TOL_PACE:
            _add(rep, 1, "FAIL", "McLaren race pace 0.795s", f"DB {mcl_gap:.3f}")
        law_c = clip("LAW", q_dep)
        mn = min_clip_driver(q_dep)
        if law_c and mn and abs(law_c - mn[1]) > TOL_CLIP:
            _add(rep, 2, "FAIL", "Lawson min clip 136m", f"LAW {law_c} min {mn}")
        fer_gap = _gap(db, wid, "Ferrari")
        if fer_gap and abs(fer_gap - 0.28) > 0.05:
            _add(rep, 3, "WARN", "Ferrari ~0.28s race pace", f"DB {fer_gap:.3f}")

    if r == 6:
        alo_st = _stints(db, r_id, "ALO")
        soft = [s for s in alo_st if s.compound and s.compound.upper() == "SOFT"]
        if soft:
            laps = (soft[0].lap_end or 0) - (soft[0].lap_start or 0) + 1
            if abs(laps - 55) > 2:
                _add(rep, 1, "WARN", "Alonso 55-lap soft stint", f"Stint laps ~{laps}")
        fer_rank = next((x.overall_rank for x in pace if x.constructor == "Ferrari"), None)
        if fer_rank != 1:
            _add(rep, 3, "FAIL", "Ferrari fastest race pace", f"Rank {fer_rank}")

    if r == 7:
        gas_ts = top_speed("GAS", q_dep)
        field_max = max((d.top_speed_kmh or 0) for d in q_dep) if q_dep else 0
        if gas_ts and abs(gas_ts - field_max) > 0.5:
            _add(rep, 2, "FAIL", "Gasly highest Q speed", f"GAS {gas_ts} max {field_max}")
        sectors = _sectors(db, q_id)
        if sectors:
            s2 = [s for s in sectors if s.sector == 2]
            if s2:
                best = min(s.best_time_s for s in s2)
                gas_s2 = next((s.best_time_s for s in s2 if s.driver == "GAS"), None)
                if gas_s2:
                    delta = gas_s2 - best
                    if abs(delta - 0.767) > 0.05:
                        _add(rep, 2, "FAIL", "Gasly S2 +0.767s", f"DB delta {delta:.3f}s")
        ham_win = pos(race_res, "HAM")
        if ham_win != 1:
            _add(rep, 3, "FAIL", "Hamilton won Barcelona", f"P{ham_win}")
        fer_rank = next((x.overall_rank for x in pace if x.constructor == "Ferrari"), None)
        if fer_rank != 1:
            _add(rep, 3, "FAIL", "Ferrari fastest race pace R7", f"Rank {fer_rank}")

    if r == 8:
        ver_ts = top_speed("VER", q_dep)
        field_max = max((d.top_speed_kmh or 0) for d in q_dep) if q_dep else 0
        if ver_ts and abs(ver_ts - field_max) > 0.5:
            _add(rep, 2, "FAIL", "Verstappen highest Q speed", f"VER {ver_ts} max {field_max}")
        pia_st = [s for s in _stints(db, r_id, "PIA") if s.stint_number == 1 or s.lap_start == 1]
        nor_st = [s for s in _stints(db, r_id, "NOR") if s.stint_number == 1 or s.lap_start == 1]
        # opening medium stint averages
        pia_m = next((s for s in _stints(db, r_id, "PIA") if s.compound and "MEDIUM" in s.compound.upper()), None)
        nor_m = next((s for s in _stints(db, r_id, "NOR") if s.compound and "MEDIUM" in s.compound.upper()), None)
        if pia_m and nor_m and pia_m.avg_pace and nor_m.avg_pace:
            diff = nor_m.avg_pace - pia_m.avg_pace
            if abs(diff - 0.2) > 0.08:
                _add(
                    rep,
                    3,
                    "FAIL",
                    "Piastri ~0.2s/lap faster opening stint",
                    f"PIA avg {pia_m.avg_pace:.2f} NOR {nor_m.avg_pace:.2f} Δ {diff:.2f}",
                )

    if r == 9:
        rus_c, ant_c = clip("RUS", q_dep), clip("ANT", q_dep)
        if rus_c and abs(rus_c - 1157) > 5:
            _add(rep, 1, "WARN", "Russell ~1157m Q clip", f"DB {rus_c}")
        rb_rank = next((x.overall_rank for x in pace if x.constructor == "Racing Bulls"), None)
        if rb_rank != 5:
            _add(rep, 2, "FAIL", "Racing Bulls 5th pace", f"Rank {rb_rank}")
        rb_gap = _gap(db, wid, "Racing Bulls")
        if rb_gap and abs(rb_gap - 1.278) > TOL_PACE:
            _add(rep, 2, "FAIL", "Racing Bulls +1.278s", f"DB {rb_gap:.3f}")
        slope = _deg_slope(db, r_id, "Alpine", "HARD")
        if slope is not None and abs(slope - 0.058) > 0.02:
            _add(rep, 3, "FAIL", "Alpine hard deg 0.058s/lap", f"DB slope {slope:.4f}")

    return rep


def format_report(reports: list[RoundReport]) -> str:
    lines: list[str] = []
    lines.append("# Insight telemetry audit (2026 season)")
    lines.append("")
    lines.append("Persisted insights in DB vs ingested Postgres telemetry. Automated checks + headline claim verification.")
    lines.append("Severity: **FAIL** = number/rank contradicts DB; **WARN** = imprecise or unverified; **OK** = matches.")
    lines.append("")

    total_fail = total_warn = 0
    for rep in reports:
        lines.append(f"## Round {rep.round}: {rep.event}")
        lines.append("")
        fails = [f for f in rep.findings if f.severity == "FAIL"]
        warns = [f for f in rep.findings if f.severity == "WARN"]
        oks = [f for f in rep.findings if f.severity == "OK"]
        total_fail += len(fails)
        total_warn += len(warns)

        # Group by slot
        by_slot: dict[int, list[Finding]] = {}
        for f in rep.findings:
            by_slot.setdefault(f.slot, []).append(f)

        for slot in sorted(by_slot):
            lines.append(f"### Insight {slot}")
            slot_fails = [f for f in by_slot[slot] if f.severity == "FAIL"]
            slot_warns = [f for f in by_slot[slot] if f.severity == "WARN"]
            if not slot_fails and not slot_warns:
                lines.append("- **Verdict:** Numbers checked — no contradictions found.")
            else:
                if slot_fails:
                    lines.append("- **Verdict:** Issues found.")
                elif slot_warns:
                    lines.append("- **Verdict:** Mostly grounded; minor flags.")
            for f in slot_fails + slot_warns:
                lines.append(f"- **{f.severity}** {f.claim}: {f.detail}")
            ok_sample = [f for f in by_slot[slot] if f.severity == "OK"][:4]
            if ok_sample:
                lines.append("- Confirmed: " + "; ".join(f"{f.claim} ({f.detail})" for f in ok_sample))
            lines.append("")

        lines.append(
            f"*Round summary: {len(fails)} FAIL, {len(warns)} WARN, {len(oks)} OK checks*"
        )
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Overall")
    lines.append("")
    lines.append(f"- **FAIL checks:** {total_fail}")
    lines.append(f"- **WARN checks:** {total_warn}")
    lines.append(
        "- Narrative/epistemic claims (e.g. \"ahead of quicker cars\", paradox framing) are not fully automatable; spot-check those manually."
    )
    return "\n".join(lines)


def main() -> None:
    reports: list[RoundReport] = []
    with Session(engine) as db:
        weekends = db.exec(
            select(RaceWeekend).where(RaceWeekend.year == YEAR).order_by(RaceWeekend.round)
        ).all()
        for w in weekends:
            insights = db.exec(
                select(Insight).where(Insight.weekend_id == w.id).order_by(Insight.slot)
            ).all()
            reports.append(audit_round(db, w, insights))
    print(format_report(reports))


if __name__ == "__main__":
    main()
