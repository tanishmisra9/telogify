import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from telogify.api.main import app
from telogify.db import get_session
from telogify.models import (
    Insight,
    RaceWeekend,
    Session as SessionRow,
    SessionResult,
    Stint,
    Subscriber,
)


@pytest.fixture
def client(test_engine):
    def override():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    with Session(test_engine) as db:
        wk = RaceWeekend(
            year=2025, round=11, circuit_name="Spielberg", country="Austria",
            event_name="Austrian Grand Prix",
        )
        db.add(wk)
        db.commit()
        db.refresh(wk)
        race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(race)
        db.commit()
        db.refresh(race)
        db.add(SessionResult(session_id=race.id, position=1, driver="NOR", constructor="McLaren", gap_to_leader=0.0))
        db.add(SessionResult(session_id=race.id, position=2, driver="LEC", constructor="Ferrari", gap_to_leader=2.5))
        db.add(Stint(session_id=race.id, driver="NOR", stint_number=1, compound="MEDIUM", lap_start=1, lap_end=20, avg_pace=70.1, lap_times_json=[70.5, 70.0, 69.9]))
        db.add(Insight(weekend_id=wk.id, slot=1, header="H1", explanation_web="W1", explanation_email="E1", source_tool_calls_json=[]))
        db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_weekends(client):
    r = client.get("/weekends")
    assert r.status_code == 200
    assert r.json()[0]["event_name"] == "Austrian Grand Prix"


def test_weekend_detail_404(client):
    assert client.get("/weekends/1999/1").status_code == 404


def test_insights(client):
    r = client.get("/weekends/2025/11/insights")
    assert [i["header"] for i in r.json()] == ["H1"]


def test_pace(client):
    stints = client.get("/weekends/2025/11/pace").json()["stints"]
    assert stints[0]["constructor"] == "McLaren"
    assert stints[0]["lap_times"] == [70.5, 70.0, 69.9]


def test_results(client):
    rows = client.get("/weekends/2025/11/results").json()
    assert [r["driver"] for r in rows] == ["NOR", "LEC"]


def test_subscribe_and_dedupe(client, test_engine):
    assert client.post("/subscribe", json={"email": "a@b.com", "followed_constructor": "Ferrari"}).json()["status"] == "subscribed"
    assert client.post("/subscribe", json={"email": "a@b.com"}).json()["status"] == "already_subscribed"
    with Session(test_engine) as db:
        from sqlmodel import select
        subs = db.exec(select(Subscriber)).all()
    assert len(subs) == 1 and subs[0].followed_constructor == "Ferrari"
