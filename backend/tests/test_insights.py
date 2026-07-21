import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlmodel import Session, select

from telogify.agent.insights import extract_trace, parse_insights, persist_insights
from telogify.models import Insight, QualiInsight, RaceWeekend
from telogify.serialize import round_prose_numbers, strip_em_dashes


def test_strip_em_dashes():
    assert strip_em_dashes("Ferrari led the way — then faded") == "Ferrari led the way, then faded"
    assert strip_em_dashes("a—b") == "a, b"
    assert strip_em_dashes("12–15 cars") == "12-15 cars"
    assert strip_em_dashes(None) is None


def test_parse_insights_tolerates_surrounding_prose():
    text = 'Here are the insights:\n[{"team":"T1","header":"H1","explanation_web":"W1","explanation_email":"E1"},' \
           '{"team":"T2","header":"H2","explanation_web":"W2","explanation_email":"E2"},' \
           '{"team":"T3","header":"H3","explanation_web":"W3","explanation_email":"E3"}]\nDone.'
    out = parse_insights(text)
    assert len(out) == 3 and out[0]["header"] == "H1"


def test_parse_insights_tolerates_trailing_prose_with_bracket():
    # The real failure: a trailing note containing ']' made find('[')..rfind(']') over-grab
    # and json.loads choke on 'Extra data'. The balanced-scan parser must stop at the array end.
    text = '[{"team":"T1","header":"H1","explanation_web":"W1","explanation_email":"E1"},' \
           '{"team":"T2","header":"H2","explanation_web":"W2","explanation_email":"E2"},' \
           '{"team":"T3","header":"H3","explanation_web":"W3","explanation_email":"E3"}]\n' \
           'Note: numbers are from tool returns [see above].'
    out = parse_insights(text)
    assert len(out) == 3 and out[2]["header"] == "H3"


def test_parse_insights_handles_bracket_inside_string_value():
    text = '[{"team":"T1","header":"Ferrari [scuderia] led S1","explanation_web":"W","explanation_email":"E"},' \
           '{"team":"T2","header":"H2","explanation_web":"W2","explanation_email":"E2"},' \
           '{"team":"T3","header":"H3","explanation_web":"W3","explanation_email":"E3"}]'
    out = parse_insights(text)
    assert out[0]["header"] == "Ferrari [scuderia] led S1"


def test_parse_insights_rejects_too_few():
    with pytest.raises(ValueError):
        parse_insights('[{"header":"H","explanation_web":"W","explanation_email":"E"}]')


def test_parse_insights_rejects_missing_keys():
    text = (
        '[{"header":"H1","explanation_web":"W1"},'
        '{"header":"H2","explanation_web":"W2"},'
        '{"header":"H3","explanation_web":"W3"}]'
    )
    with pytest.raises(ValueError, match="missing keys"):
        parse_insights(text)


def test_parse_insights_rejects_no_json_array():
    with pytest.raises(ValueError, match="no JSON array"):
        parse_insights("No insights here, just prose.")


def test_parse_insights_truncates_to_three():
    items = [
        {"team": f"T{i}", "header": f"H{i}", "explanation_web": f"W{i}", "explanation_email": f"E{i}"}
        for i in range(1, 6)
    ]
    out = parse_insights(json.dumps(items))
    assert len(out) == 3 and out[0]["header"] == "H1" and out[2]["header"] == "H3"


def test_extract_trace_handles_block_content():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_pace", "args": {}, "id": "c1", "type": "tool_call"}],
        ),
        type("ToolMsg", (), {"type": "tool", "tool_call_id": "c1", "content": [{"text": '{"ok": true}'}]})(),
    ]
    trace = extract_trace(messages)
    assert trace[0]["result"] == '{"ok": true}'


def test_extract_trace_preserves_multiple_calls_in_order():
    from langchain_core.messages import ToolMessage

    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_pace", "args": {"driver": "VER"}, "id": "c1", "type": "tool_call"},
                {"name": "get_straight_speed", "args": {"driver": "LEC"}, "id": "c2", "type": "tool_call"},
            ],
        ),
        ToolMessage(content='{"median": 90.1}', tool_call_id="c1"),
        ToolMessage(content='{"max_speed_kmh": 330}', tool_call_id="c2"),
    ]
    trace = extract_trace(messages)
    assert [t["tool"] for t in trace] == ["get_pace", "get_straight_speed"]
    assert "90.1" in trace[0]["result"]
    assert "330" in trace[1]["result"]


def test_extract_trace_pairs_calls_with_returns():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_straight_speed", "args": {"driver": "LEC"}, "id": "c1", "type": "tool_call"}],
        ),
        ToolMessage(content='{"max_speed_kmh": 330.5}', tool_call_id="c1"),
    ]
    trace = extract_trace(messages)
    assert trace == [{"tool": "get_straight_speed", "args": {"driver": "LEC"}, "result": '{"max_speed_kmh": 330.5}'}]


def test_round_prose_numbers_strips_long_floats():
    text = (
        "Hamilton averaged 81.98835714285714 seconds while Ferrari was "
        "0.10499999999998977 seconds per lap off Mercedes."
    )
    out = round_prose_numbers(text)
    assert "35714285714" not in out
    assert "99999999999998977" not in out
    assert "82" in out
    assert "0.105" in out


def test_persist_insights_rounds_long_decimals(db_session):
    wk = RaceWeekend(year=2025, round=16, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    insights = [
        {
            "header": "H1",
            "explanation_web": "Pace was 0.10499999999998977 seconds off.",
            "explanation_email": "E1",
        },
        {"header": "H2", "explanation_web": "W2", "explanation_email": "E2"},
        {"header": "H3", "explanation_web": "W3", "explanation_email": "E3"},
    ]
    trace = [{"tool": "t", "args": {}, "result": "{}"}]
    persist_insights(wk.id, insights, trace, db_session)

    stored = db_session.exec(select(Insight).where(Insight.weekend_id == wk.id, Insight.slot == 1)).one()
    assert "999999" not in stored.explanation_web
    assert "0.105" in stored.explanation_web


def test_persist_insights_strips_dashes_and_logs_trace(db_session):
    wk = RaceWeekend(year=2025, round=11, circuit_name="Spielberg", country="Austria", event_name="A")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    insights = [
        {"header": f"H{i} — claim", "explanation_web": f"W{i} 12 km/h (7 mph)", "explanation_email": f"E{i}"}
        for i in range(1, 4)
    ]
    trace = [{"tool": "get_straight_speed", "args": {}, "result": '{"max_speed_kmh": 330.5}'}]

    rows = persist_insights(wk.id, insights, trace, db_session)

    stored = db_session.exec(select(Insight).where(Insight.weekend_id == wk.id).order_by(Insight.slot)).all()
    assert [r.slot for r in stored] == [1, 2, 3]
    assert "—" not in stored[0].header  # serializer pass applied
    assert stored[0].header == "H1, claim"
    # every insight carries the auditable trace
    assert stored[0].source_tool_calls_json == trace
    assert "330.5" in stored[0].source_tool_calls_json[0]["result"]


def test_parse_insights_supports_count_two_with_team_key():
    text = json.dumps(
        [
            {"team": "Mercedes", "header": "H1", "explanation_web": "W1", "explanation_email": "E1"},
            {"team": "Ferrari", "header": "H2", "explanation_web": "W2", "explanation_email": "E2"},
        ]
    )
    out = parse_insights(text, count=2, required_keys=("team", "header", "explanation_web", "explanation_email"))
    assert len(out) == 2
    assert out[0]["team"] == "Mercedes"


def test_parse_insights_count_two_rejects_missing_team():
    text = json.dumps(
        [
            {"header": "H1", "explanation_web": "W1", "explanation_email": "E1"},
            {"header": "H2", "explanation_web": "W2", "explanation_email": "E2"},
        ]
    )
    with pytest.raises(ValueError, match="missing keys"):
        parse_insights(text, count=2, required_keys=("team", "header", "explanation_web", "explanation_email"))


def test_persist_insights_targets_quali_insight_model_with_team(db_session):
    wk = RaceWeekend(year=2026, round=8, circuit_name="Spielberg", country="Austria", event_name="A")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    insights = [
        {"team": "Mercedes", "header": "H1", "explanation_web": "W1", "explanation_email": "E1"},
        {"team": "Ferrari", "header": "H2 — claim", "explanation_web": "W2", "explanation_email": "E2"},
    ]
    trace = [{"tool": "get_quali_character", "args": {}, "result": "{}"}]

    rows = persist_insights(wk.id, insights, trace, db_session, model=QualiInsight, count=2)

    assert len(rows) == 2
    stored = db_session.exec(
        select(QualiInsight).where(QualiInsight.weekend_id == wk.id).order_by(QualiInsight.slot)
    ).all()
    assert [r.slot for r in stored] == [1, 2]
    assert [r.team for r in stored] == ["Mercedes", "Ferrari"]
    assert "—" not in stored[1].header  # serializer pass still applied

    # the race Insight table is untouched by a quali persist
    assert db_session.exec(select(Insight).where(Insight.weekend_id == wk.id)).all() == []
