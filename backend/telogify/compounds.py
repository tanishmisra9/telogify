"""Tyre compound validity, shared by ingest and analysis (neutral: imports nothing)."""

# FastF1 sometimes has no tyre data for a stint and emits missing values or text such as
# "None", "UNKNOWN" or "TEST_UNKNOWN" instead of a compound. An allowlist, not a denylist, so a
# new junk value can't slip through as a fake tyre.
KNOWN_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"})


def is_known_compound(compound: str | None) -> bool:
    """True only for a real tyre compound. Callers drop anything else rather than show a fake tyre."""
    return isinstance(compound, str) and compound.strip().upper() in KNOWN_COMPOUNDS
