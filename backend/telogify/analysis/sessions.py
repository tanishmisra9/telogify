"""Session selection helpers shared across analysis and API layers."""

from telogify.models import Session


def pick_session(sessions: list[Session], priority: tuple[str, ...]) -> Session | None:
    """Return the session whose type appears earliest in priority.

    When both R and SPRINT (or Q and SQ) exist, callers pass an explicit order so
    selection is deterministic instead of depending on DB row order.
    """
    by_type = {s.session_type: s for s in sessions}
    for session_type in priority:
        if session_type in by_type:
            return by_type[session_type]
    return None
