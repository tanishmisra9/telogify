"""Tests for deterministic session selection."""

from telogify.analysis.sessions import pick_session
from telogify.models import Session


def _session(session_type: str, session_id: int = 1) -> Session:
    return Session(id=session_id, weekend_id=1, session_type=session_type)


def test_pick_session_prefers_r_over_sprint():
    sessions = [_session("SPRINT", 1), _session("R", 2)]
    assert pick_session(sessions, ("R", "SPRINT")).session_type == "R"


def test_pick_session_prefers_q_over_sq():
    sessions = [_session("SQ", 1), _session("Q", 2)]
    assert pick_session(sessions, ("Q", "SQ")).session_type == "Q"


def test_pick_session_returns_none_when_absent():
    assert pick_session([_session("FP1")], ("R", "SPRINT")) is None
