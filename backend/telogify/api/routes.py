"""Read endpoints for the three frontend surfaces, plus subscribe."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from telogify.db import get_session
from telogify.models import (
    Insight,
    RaceWeekend,
    Session as SessionRow,
    SessionResult,
    Stint,
    Subscriber,
)

router = APIRouter()


class SubscribeIn(BaseModel):
    email: str
    followed_constructor: str | None = None


def _weekend(db: Session, year: int, round: int) -> RaceWeekend:
    w = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year, RaceWeekend.round == round)
    ).first()
    if w is None:
        raise HTTPException(status_code=404, detail="weekend not found")
    return w


def _race_session(db: Session, weekend_id: int) -> SessionRow | None:
    return db.exec(
        select(SessionRow).where(
            SessionRow.weekend_id == weekend_id, SessionRow.session_type == "R"
        )
    ).first()


def _driver_constructor(db: Session, session_id: int) -> dict[str, str]:
    rows = db.exec(select(SessionResult).where(SessionResult.session_id == session_id)).all()
    return {r.driver: r.constructor for r in rows if r.constructor}


@router.get("/weekends")
def list_weekends(db: Session = Depends(get_session)):
    rows = db.exec(
        select(RaceWeekend).order_by(RaceWeekend.year.desc(), RaceWeekend.round.desc())
    ).all()
    return [
        {
            "id": w.id,
            "year": w.year,
            "round": w.round,
            "event_name": w.event_name,
            "circuit_name": w.circuit_name,
            "country": w.country,
        }
        for w in rows
    ]


@router.get("/weekends/{year}/{round}")
def weekend_detail(year: int, round: int, db: Session = Depends(get_session)):
    w = _weekend(db, year, round)
    return {
        "id": w.id,
        "year": w.year,
        "round": w.round,
        "event_name": w.event_name,
        "circuit_name": w.circuit_name,
        "country": w.country,
    }


@router.get("/weekends/{year}/{round}/insights")
def weekend_insights(year: int, round: int, db: Session = Depends(get_session)):
    w = _weekend(db, year, round)
    rows = db.exec(
        select(Insight).where(Insight.weekend_id == w.id).order_by(Insight.slot)
    ).all()
    return [
        {"slot": r.slot, "header": r.header, "explanation_web": r.explanation_web} for r in rows
    ]


@router.get("/weekends/{year}/{round}/pace")
def weekend_pace(year: int, round: int, db: Session = Depends(get_session)):
    w = _weekend(db, year, round)
    race = _race_session(db, w.id)
    if race is None:
        return {"stints": []}
    dc = _driver_constructor(db, race.id)
    stints = db.exec(select(Stint).where(Stint.session_id == race.id)).all()
    return {
        "stints": [
            {
                "driver": s.driver,
                "constructor": dc.get(s.driver),
                "stint_number": s.stint_number,
                "compound": s.compound,
                "lap_start": s.lap_start,
                "lap_times": s.lap_times_json,
            }
            for s in stints
        ]
    }


@router.get("/weekends/{year}/{round}/results")
def weekend_results(year: int, round: int, db: Session = Depends(get_session)):
    w = _weekend(db, year, round)
    race = _race_session(db, w.id)
    if race is None:
        return []
    rows = db.exec(
        select(SessionResult)
        .where(SessionResult.session_id == race.id)
        .order_by(SessionResult.position)
    ).all()
    return [
        {
            "position": r.position,
            "driver": r.driver,
            "constructor": r.constructor,
            "gap_to_leader": r.gap_to_leader,
            "status": r.status,
        }
        for r in rows
    ]


@router.post("/subscribe")
def subscribe(body: SubscribeIn, db: Session = Depends(get_session)):
    existing = db.exec(select(Subscriber).where(Subscriber.email == body.email)).first()
    if existing:
        return {"status": "already_subscribed"}
    db.add(Subscriber(email=body.email, followed_constructor=body.followed_constructor))
    db.commit()
    return {"status": "subscribed"}
