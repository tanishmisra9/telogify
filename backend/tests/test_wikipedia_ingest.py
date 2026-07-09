"""Tests for Wikipedia ingest + agent tool read path."""

import json
from pathlib import Path

import httpx
from sqlmodel import Session, select

from telogify.agent.tools import build_tools
from telogify.ingest.loader import WeekendData
from telogify.ingest.wikipedia import WikipediaClient, fetch_weekend_recap, store_weekend_recap
from telogify.models import RaceWeekend, Session as SessionRow, WeekendRecap

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wikipedia"


def _wikitext(name: str) -> str:
    return (_FIXTURES / name).read_text()


class _FakeClient(WikipediaClient):
    def __init__(self, wikitext: str):
        super().__init__()
        self._wikitext = wikitext

    def resolve_page(self, title: str):
        return "2026 Chinese Grand Prix", 12345

    def search_grand_prix(self, query: str):
        return None

    def fetch_wikitext(self, title: str):
        return self._wikitext

    def fetch_toc_sections(self, title: str):
        return []

    def fetch_section_wikitext(self, title: str, section_index: str):
        return None


def test_fetch_weekend_recap_parses_fixture():
    weekend = RaceWeekend(
        id=1, year=2026, round=2, circuit_name="Shanghai", country="China", event_name="Chinese Grand Prix"
    )
    title, page_id, sessions = fetch_weekend_recap(
        weekend,
        {"Q", "R"},
        client=_FakeClient(_wikitext("2026_chinese_gp.wikitext")),
    )
    assert title == "2026 Chinese Grand Prix"
    assert page_id == 12345
    assert sessions["R"]["present"] is True
    assert any("coolant" in f["text"].lower() for f in sessions["R"]["facts"])


def test_store_weekend_recap_persists(db_session, monkeypatch):
    wk = RaceWeekend(
        year=2026, round=2, circuit_name="Shanghai", country="China", event_name="Chinese Grand Prix"
    )
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    for st in ("Q", "R"):
        db_session.add(SessionRow(weekend_id=wk.id, session_type=st, status="loaded"))
    db_session.commit()

    fake = _FakeClient(_wikitext("2026_chinese_gp.wikitext"))

    def _fetch(weekend, present, client=None, protagonist_drivers=None):
        return fetch_weekend_recap(weekend, present, client=fake, protagonist_drivers=protagonist_drivers)

    monkeypatch.setattr("telogify.ingest.wikipedia.fetch_weekend_recap", _fetch)
    data = WeekendData(weekend=wk, sessions={"Q": None, "R": None})
    store_weekend_recap(data, db_session)

    row = db_session.exec(select(WeekendRecap).where(WeekendRecap.weekend_id == wk.id)).first()
    assert row is not None
    assert row.page_title == "2026 Chinese Grand Prix"
    assert row.sessions_json["R"]["present"] is True


def test_get_weekend_recap_tool_reads_db(db_session):
    wk = RaceWeekend(year=2026, round=2, circuit_name="X", country="Y", event_name="Chinese Grand Prix")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    db_session.add(
        WeekendRecap(
            weekend_id=wk.id,
            page_title="2026 Chinese Grand Prix",
            page_id=1,
            sessions_json={
                "R": {
                    "present": True,
                    "summary": "Verstappen retired on lap 45 with a coolant leak.",
                    "facts": [
                        {
                            "kind": "retirement",
                            "lap": 45,
                            "drivers": ["VER"],
                            "text": "Verstappen retired on lap 45 with a coolant leak.",
                        }
                    ],
                }
            },
        )
    )
    db_session.commit()

    tools = {t.name: t for t in build_tools(2026, 2, session_factory=lambda: db_session)}
    out = json.loads(tools["get_weekend_recap"].invoke({}))
    assert out["source"] == "wikipedia"
    assert out["sessions"]["R"]["facts"][0]["lap"] == 45


def test_store_weekend_recap_swallows_http_errors(db_session, monkeypatch):
    wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    def _boom(*args, **kwargs):
        raise httpx.HTTPError("network down")

    monkeypatch.setattr("telogify.ingest.wikipedia.fetch_weekend_recap", _boom)
    data = WeekendData(weekend=wk, sessions={})
    store_weekend_recap(data, db_session)  # must not raise

    row = db_session.exec(select(WeekendRecap).where(WeekendRecap.weekend_id == wk.id)).first()
    assert row is not None
    assert row.sessions_json == {}
