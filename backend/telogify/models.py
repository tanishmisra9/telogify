"""SQLModel tables. Race weekend is the top entity, above session."""

from datetime import datetime

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class RaceWeekend(SQLModel, table=True):
    __tablename__ = "race_weekend"
    __table_args__ = (UniqueConstraint("year", "round", name="uq_weekend_year_round"),)

    id: int | None = Field(default=None, primary_key=True)
    year: int = Field(index=True)
    round: int = Field(index=True)
    circuit_name: str
    country: str
    event_name: str


class Session(SQLModel, table=True):
    __tablename__ = "session"
    __table_args__ = (
        UniqueConstraint("weekend_id", "session_type", name="uq_session_weekend_type"),
    )

    id: int | None = Field(default=None, primary_key=True)
    weekend_id: int = Field(foreign_key="race_weekend.id", index=True)
    session_type: str  # FP1/FP2/FP3/Q/SQ/SPRINT/R
    status: str | None = None


class Fingerprint(SQLModel, table=True):
    __tablename__ = "fingerprint"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    corner_number: int = Field(index=True)
    brake_point: float | None = None
    trail_brake_dur: float | None = None
    min_speed: float | None = None
    throttle_point: float | None = None
    throttle_ramp: float | None = None
    steer_at_apex: float | None = None
    gear: int | None = None
    clean_lap_count: int = 0
    compound: str | None = None


class StraightSegment(SQLModel, table=True):
    __tablename__ = "straight_segment"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    drs_zone_id: int = Field(index=True)
    max_speed_kmh: float | None = None
    trap_speed_kmh: float | None = None


class Stint(SQLModel, table=True):
    __tablename__ = "stint"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    stint_number: int
    compound: str | None = None
    lap_start: int | None = None
    lap_end: int | None = None
    avg_pace: float | None = None
    lap_times_json: list = Field(default_factory=list, sa_column=Column(JSON))
    # Tyre age (laps on the current set) aligned index-for-index with lap_times_json,
    # so degradation analysis can regress fuel-corrected time against actual tyre age.
    tyre_ages_json: list = Field(default_factory=list, sa_column=Column(JSON))


class SessionResult(SQLModel, table=True):
    __tablename__ = "session_result"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    position: int | None = None
    driver: str
    constructor: str | None = None
    gap_to_leader: float | None = None
    total_time_s: float | None = None  # winner's total race time; None for everyone else
    laps: float | None = None
    status: str | None = None


class SectorBest(SQLModel, table=True):
    __tablename__ = "sector_best"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    sector: int  # 1, 2, or 3
    best_time_s: float


class QualiCharacter(SQLModel, table=True):
    __tablename__ = "quali_character"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    constructor: str | None = None
    lap_time_s: float | None = None
    top_speed_kmh: float | None = None
    min_speed_kmh: float | None = None
    full_throttle_pct: float | None = None
    # {corner_number (str): min_speed_kmh} on this lap, for every corner. The "fastest
    # corner" shown in the car-character table is picked once (the corner where the
    # compared field's speed is highest) so every team is compared through the same
    # corner, not each team's own personal-best corner.
    corner_speeds_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Attribution(SQLModel, table=True):
    __tablename__ = "attribution"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    corner_number: int = Field(index=True)
    speed_class: str | None = None  # high/mid/low
    constructor_a: str
    constructor_b: str
    delta_s: float | None = None
    car_pct: float | None = None
    driver_pct: float | None = None
    confidence: float | None = None


class ConstructorIndex(SQLModel, table=True):
    __tablename__ = "constructor_index"

    id: int | None = Field(default=None, primary_key=True)
    weekend_id: int = Field(foreign_key="race_weekend.id", index=True)
    constructor: str = Field(index=True)
    high_score: float | None = None
    mid_score: float | None = None
    low_score: float | None = None
    overall_rank: int | None = None
    lap_deficit_s: float | None = None


class CandidateInsight(SQLModel, table=True):
    __tablename__ = "candidate_insight"

    id: int | None = Field(default=None, primary_key=True)
    weekend_id: int = Field(foreign_key="race_weekend.id", index=True)
    rank: int | None = None
    category: str | None = None
    signal_type: str = Field(index=True)
    magnitude: float | None = None
    confidence: float | None = None
    robustness_score: float | None = None
    source_refs_json: dict | None = Field(default=None, sa_column=Column(JSON))


class Insight(SQLModel, table=True):
    __tablename__ = "insight"

    id: int | None = Field(default=None, primary_key=True)
    weekend_id: int = Field(foreign_key="race_weekend.id", index=True)
    slot: int  # 1-3
    header: str
    explanation_web: str
    explanation_email: str
    source_tool_calls_json: list = Field(default_factory=list, sa_column=Column(JSON))


class Subscriber(SQLModel, table=True):
    __tablename__ = "subscriber"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    followed_constructor: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
