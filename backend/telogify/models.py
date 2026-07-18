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
    # Gap to the car ahead in seconds (None if unknown, e.g. race leader), aligned
    # index-for-index with lap_times_json, so clean-air pace can exclude dirty-air laps.
    gaps_to_car_ahead_json: list = Field(default_factory=list, sa_column=Column(JSON))


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
    # Qualifying-segment best times (Q/SQ sessions only; None everywhere else, and None for a
    # segment a driver did not reach, e.g. a Q1-eliminated driver has no q2/q3_time_s).
    q1_time_s: float | None = None
    q2_time_s: float | None = None
    q3_time_s: float | None = None


class SectorBest(SQLModel, table=True):
    __tablename__ = "sector_best"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    sector: int  # 1, 2, or 3
    best_time_s: float


class RaceControlEvent(SQLModel, table=True):
    """A notable on-track event from official race control messages: collision, incident,
    penalty, safety car, forced-off, or retirement. One row per car involved (driver is the
    3-letter code, or None for a track-wide event like a safety car)."""

    __tablename__ = "race_control_event"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    lap: int | None = None
    driver: str | None = Field(default=None, index=True)
    kind: str  # collision | incident | penalty | safety_car | forced_off | retirement
    message: str


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


class DeploymentTrace(SQLModel, table=True):
    """Per-driver ERS deployment / clipping on a representative qualifying lap, inferred from the
    speed trace (F1 broadcasts no battery state). `total_clip_m` / `max_clip_m` compare cars: a car
    that clips more runs out of electrical deployment sooner down the straights and is passable there."""

    __tablename__ = "deployment_trace"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    constructor: str | None = None
    top_speed_kmh: float | None = None
    total_clip_m: float = 0.0
    total_depletion_m: float = 0.0
    total_superclip_m: float = 0.0
    max_clip_m: float = 0.0
    max_clip_severity_ms2: float = 0.0
    n_straights: int = 0
    n_clips: int = 0
    # per-straight: start/end, peak, clip_m, depletion_m, superclip_m, drop_kmh, end_reason,
    # is_clip, clip_type, clip_severity_ms2, method
    straights_json: list = Field(default_factory=list, sa_column=Column(JSON))


class QualiTrace(SQLModel, table=True):
    """Per-driver distance-resampled telemetry from the MAIN Qualifying session (Q only, never
    SQ) representative lap, for "The fight to pole". Stores every driver's trace, not just
    P1/P2: the API and frontend currently only serve/render the top two qualifiers, but this
    keeps the door open for comparing more or different drivers later without re-ingesting.

    grid_m/corners_json are duplicated verbatim on every driver row for a session rather than
    normalized into a session-level table, matching this codebase's existing self-contained-row
    style (see DeploymentTrace.straights_json above) -- a session has ~20 rows with a ~100-float
    array each, not worth a join.
    """

    __tablename__ = "quali_trace"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    constructor: str | None = None
    lap_time_s: float | None = None
    is_pole: bool = False
    grid_m: list = Field(default_factory=list, sa_column=Column(JSON))
    corners_json: list = Field(default_factory=list, sa_column=Column(JSON))  # [{number, distance_m}]
    # speed_kmh/throttle_pct/delta_s: resampled onto grid_m BY LAP FRACTION, so every point is a
    # driver's real telemetry at that fraction of their own lap (see analysis/quali_trace.py).
    # delta_s is 0.0 throughout for the pole row; the final point is each lap's finish line, so a
    # driver's last delta_s is their true lap-time gap to pole.
    speed_kmh: list = Field(default_factory=list, sa_column=Column(JSON))
    throttle_pct: list = Field(default_factory=list, sa_column=Column(JSON))
    delta_s: list = Field(default_factory=list, sa_column=Column(JSON))


class AccelSample(SQLModel, table=True):
    """Full-throttle, no-brake, low-lateral-g (speed, longitudinal acceleration) points from one
    representative race lap per driver, for the season-wide ERS deployment/harvesting scatter.
    Longitudinal accel is derived the same way as deployment.py's clip detector; lateral accel is
    derived from position curvature (see analysis/kinematics.py) since FastF1 exposes neither
    directly. Data selection follows Mirco Bartolozzi's (fdataanalysis) stated approach."""

    __tablename__ = "accel_sample"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    driver: str = Field(index=True)
    constructor: str | None = None
    # Index-aligned (speed_kmh, longitudinal accel m/s^2) pairs.
    speed_kmh_json: list = Field(default_factory=list, sa_column=Column(JSON))
    longitudinal_accel_ms2_json: list = Field(default_factory=list, sa_column=Column(JSON))


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
    model_used: str | None = None  # e.g. "anthropic / claude-sonnet-5", from configured_llm_label()
    prompt_version: str | None = None  # agent.prompts.PROMPT_VERSION at generation time


class QualiInsight(SQLModel, table=True):
    __tablename__ = "quali_insight"

    id: int | None = Field(default=None, primary_key=True)
    weekend_id: int = Field(foreign_key="race_weekend.id", index=True)
    slot: int  # 1-2
    team: str | None = None
    header: str
    explanation_web: str
    explanation_email: str
    source_tool_calls_json: list = Field(default_factory=list, sa_column=Column(JSON))
    model_used: str | None = None
    prompt_version: str | None = None


class SeasonDeploymentInsight(SQLModel, table=True):
    """One LLM-written verdict per power-unit manufacturer for the season deployment section,
    ranked best-to-worst (rank 1 = best) by analysis/season_deployment.rank_groups_best_to_worst.
    Recomputed idempotently per year: delete + reinsert."""

    __tablename__ = "season_deployment_insight"

    id: int | None = Field(default=None, primary_key=True)
    year: int = Field(index=True)
    rank: int  # 1 = best PU this season
    pu_name: str  # power-unit manufacturer, e.g. "Mercedes"
    works_team: str  # team whose color marks the row
    teams_json: list = Field(default_factory=list, sa_column=Column(JSON))
    header: str
    explanation_web: str
    source_metrics_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    model_used: str | None = None
    prompt_version: str | None = None


class Subscriber(SQLModel, table=True):
    __tablename__ = "subscriber"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    followed_constructor: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
