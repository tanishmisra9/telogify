"""Wikipedia Action API fetch + weekend recap persistence."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.config import settings
from telogify.ingest.loader import WeekendData
from telogify.ingest.wikipedia_parse import (
    SESSION_TYPES,
    build_recap_payload,
    decode_toc_line,
    map_sections_to_sessions,
    protagonist_drivers_from_swings,
    split_wikitext_sections,
)
from telogify.models import Session, SessionResult, WeekendRecap

logger = logging.getLogger(__name__)

_API_BASE = "https://en.wikipedia.org/w/api.php"
_RECAP_SESSIONS = frozenset(SESSION_TYPES)


class WikipediaClient:
    """Serial MediaWiki Action API client (one connection, serial GETs)."""

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        self._user_agent = user_agent or settings.wikipedia_user_agent
        self._timeout = timeout or httpx.Timeout(15.0, connect=30.0)
        self._client = httpx.Client(
            headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip"},
            timeout=self._timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WikipediaClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _get(self, params: dict) -> dict:
        base = {
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        }
        response = self._client.get(_API_BASE, params={**base, **params})
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("info", str(data["error"])))
        if data.get("errors"):
            raise RuntimeError(str(data["errors"]))
        return data

    def resolve_page(self, title: str) -> tuple[str, int] | None:
        data = self._get(
            {
                "action": "query",
                "redirects": "1",
                "titles": title,
                "prop": "info",
            }
        )
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return None
        page = pages[0]
        if page.get("missing"):
            return None
        return page["title"], int(page["pageid"])

    def search_grand_prix(self, query: str) -> tuple[str, int] | None:
        data = self._get(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": "0",
                "srlimit": "5",
            }
        )
        for hit in data.get("query", {}).get("search", []):
            title = hit.get("title", "")
            if "Grand Prix" in title:
                resolved = self.resolve_page(title)
                if resolved:
                    return resolved
        return None

    def fetch_wikitext(self, title: str) -> str | None:
        data = self._get(
            {
                "action": "query",
                "redirects": "1",
                "titles": title,
                "prop": "revisions",
                "rvslots": "main",
                "rvprop": "content",
            }
        )
        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return None
        revisions = pages[0].get("revisions") or []
        if not revisions:
            return None
        slots = revisions[0].get("slots", {})
        main = slots.get("main", {})
        return main.get("content")

    def fetch_section_wikitext(self, title: str, section_index: str) -> str | None:
        data = self._get(
            {
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "section": section_index,
            }
        )
        return data.get("parse", {}).get("wikitext")

    def fetch_toc_sections(self, title: str) -> list[tuple[str, str]]:
        data = self._get(
            {
                "action": "parse",
                "page": title,
                "prop": "tocdata",
            }
        )
        toc = data.get("parse", {}).get("tocdata", {})
        out: list[tuple[str, str]] = []
        for sec in toc.get("sections", []):
            idx = sec.get("index")
            line = sec.get("line")
            if idx and line:
                out.append((str(idx), decode_toc_line(line)))
        return out


def _resolve_title(weekend, client: WikipediaClient) -> tuple[str, int] | None:
    if weekend.wikipedia_title:
        return client.resolve_page(weekend.wikipedia_title)
    primary = f"{weekend.year} {weekend.event_name}"
    resolved = client.resolve_page(primary)
    if resolved:
        return resolved
    return client.search_grand_prix(f"{weekend.year} {weekend.event_name} Grand Prix")


def _fetch_wikitext_with_fallback(client: WikipediaClient, title: str) -> str | None:
    wikitext = client.fetch_wikitext(title)
    if not wikitext:
        return None
    sections = split_wikitext_sections(wikitext)
    if map_sections_to_sessions(sections):
        return wikitext

    toc = client.fetch_toc_sections(title)
    if not toc:
        return wikitext

    rebuilt_parts: list[str] = []
    for idx, heading in toc:
        body = client.fetch_section_wikitext(title, idx)
        if body:
            rebuilt_parts.append(f"== {heading} ==\n{body}")
    return "\n\n".join(rebuilt_parts) if rebuilt_parts else wikitext


def _grid_finish_swings(weekend_id: int, db: DBSession) -> dict[str, int]:
    """Per-driver grid (Q) to finish (R) position swing: positive = positions gained."""
    quali = db.exec(
        select(Session).where(Session.weekend_id == weekend_id, Session.session_type == "Q")
    ).first()
    race = db.exec(
        select(Session).where(Session.weekend_id == weekend_id, Session.session_type == "R")
    ).first()
    if quali is None or race is None:
        return {}
    grid = {
        r.driver: r.position
        for r in db.exec(select(SessionResult).where(SessionResult.session_id == quali.id)).all()
        if r.driver and r.position is not None
    }
    swings: dict[str, int] = {}
    for r in db.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all():
        start = grid.get(r.driver)
        if start is None or r.position is None or r.driver is None:
            continue
        swings[r.driver] = start - r.position
    return swings


def fetch_weekend_recap(
    weekend,
    session_types_present: set[str],
    client: WikipediaClient | None = None,
    protagonist_drivers: frozenset[str] | None = None,
) -> tuple[str | None, int | None, dict]:
    """Fetch and parse recap. Returns (page_title, page_id, sessions_json)."""

    def _run(api: WikipediaClient) -> tuple[str | None, int | None, dict]:
        resolved = _resolve_title(weekend, api)
        if not resolved:
            return None, None, {}
        page_title, page_id = resolved
        wikitext = _fetch_wikitext_with_fallback(api, page_title)
        if not wikitext:
            return page_title, page_id, {}
        present = session_types_present & _RECAP_SESSIONS
        sessions_json = build_recap_payload(
            wikitext, present, protagonist_drivers=protagonist_drivers
        )
        return page_title, page_id, sessions_json

    if client is not None:
        return _run(client)
    with WikipediaClient() as api:
        return _run(api)


def store_weekend_recap(data: WeekendData, db: DBSession) -> None:
    """Idempotent: delete + insert recap for this weekend. Never raises on fetch failure."""
    if not settings.wikipedia_recap_enabled:
        return

    weekend_id = data.weekend.id
    if weekend_id is None:
        return

    session_rows = db.exec(
        select(Session.session_type).where(Session.weekend_id == weekend_id)
    ).all()
    present = {row for row in session_rows if row in _RECAP_SESSIONS}

    page_title: str | None = None
    page_id: int | None = None
    sessions_json: dict = {}

    swings = _grid_finish_swings(weekend_id, db)
    protagonists = protagonist_drivers_from_swings(swings)

    try:
        page_title, page_id, sessions_json = fetch_weekend_recap(
            data.weekend, present, protagonist_drivers=protagonists
        )
    except httpx.HTTPError as exc:
        logger.warning("Wikipedia fetch failed for weekend %s: %s", weekend_id, exc)
    except RuntimeError as exc:
        logger.warning("Wikipedia API error for weekend %s: %s", weekend_id, exc)

    db.exec(delete(WeekendRecap).where(WeekendRecap.weekend_id == weekend_id))
    db.add(
        WeekendRecap(
            weekend_id=weekend_id,
            page_title=page_title,
            page_id=page_id,
            fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
            sessions_json=sessions_json,
        )
    )
    db.commit()
