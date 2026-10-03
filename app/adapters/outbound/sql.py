"""SQL persistence (SQLite or Postgres) via SQLAlchemy Core. Write-behind cache over InMemoryRepo:
load everything on start, `commit()` writes the diff since the last commit.
Single-process only (1 uvicorn worker). Datetimes as ISO strings (keeps tz), lists/dicts as JSON."""
import logging
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import OperationalError
from sqlalchemy import JSON, Boolean, Column, Float, Integer, MetaData, String, Table, create_engine, delete, insert, \
    select, update

from app.adapters.outbound.memory import InMemoryRepo
from app.domain.enums import (
    CurrentState,
    FeatureKey,
    Nature,
    ObservationSource,
    ObservationValue,
    QueueStatus,
    Role,
    Severity,
    StateValue,
    ValidationStatus,
)
from app.domain.model import (
    FeatureStateRecord,
    GeoPoint,
    Observation,
    Photo,
    Place,
    QueueItem,
    Report,
    Session,
    User,
)

log = logging.getLogger(__name__)
md = MetaData()

users = Table("users", md, Column("id", String, primary_key=True), Column("seq", Integer),
              Column("display_name", String), Column("role", String), Column("username", String),
              Column("email", String), Column("google_sub", String))
sessions = Table("sessions", md, Column("token", String, primary_key=True), Column("user_id", String),
                 Column("expires_at", String))
places = Table("places", md, Column("id", String, primary_key=True), Column("seq", Integer), Column("name", String),
               Column("category", String), Column("lat", Float), Column("lon", Float),
               Column("short_description", String), Column("address", String), Column("owner_id", String),
               Column("external_id", String))
states = Table("feature_states", md, Column("place_id", String, primary_key=True),
               Column("feature", String, primary_key=True), Column("state", String), Column("confidence", Float),
               Column("temporary", Boolean), Column("last_verified", String), Column("sources_count", Integer),
               Column("validation", String), Column("active_observation_id", String))
observations = Table("observations", md, Column("id", String, primary_key=True), Column("seq", Integer),
                     Column("place_id", String, index=True), Column("feature", String), Column("value", String),
                     Column("source", String), Column("author_id", String), Column("created_at", String),
                     Column("temporary", Boolean), Column("comment", String), Column("evidence_ids", JSON),
                     Column("votes", JSON), Column("validation", String), Column("confidence", Float),
                     Column("report_id", String))
reports = Table("reports", md, Column("id", String, primary_key=True), Column("seq", Integer),
                Column("place_id", String), Column("author_id", String), Column("element", String),
                Column("current_state", String), Column("severity", String), Column("nature", String),
                Column("description", String), Column("created_at", String), Column("photo_ids", JSON),
                Column("status", String), Column("observation_ids", JSON))
photos = Table("photos", md, Column("id", String, primary_key=True), Column("seq", Integer), Column("path", String),
               Column("url", String), Column("original_name", String))
queue = Table("queue_items", md, Column("id", String, primary_key=True), Column("seq", Integer),
              Column("place_id", String), Column("feature", String), Column("created_at", String),
              Column("observation_ids", JSON), Column("type", String), Column("status", String),
              Column("decision", String))

PK = {t.name: [c.name for c in t.primary_key.columns] for t in md.sorted_tables}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class SqlRepo(InMemoryRepo):
    def __init__(self, url: str, connect_retries: int = 15, retry_pause_s: float = 2.0):
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, pool_pre_ping=True)
        for attempt in range(1, connect_retries + 1):  # Postgres in docker may still be booting
            try:
                md.create_all(self.engine)
                break
            except OperationalError:
                if attempt == connect_retries:
                    raise
                log.warning("database not ready (attempt %s/%s), retrying…", attempt, connect_retries)
                time.sleep(retry_pause_s)
        super().__init__()
        self._snapshot: dict[tuple[str, tuple], dict] = {}
        self._load()

    # ------------------------------------------------------------------ port extras
    def commit(self) -> None:
        current = {(t.name, tuple(row[k] for k in PK[t.name])): (t, row) for t, row in self._rows()}
        with self.engine.begin() as conn:
            for name, key in self._snapshot.keys() - current.keys():
                table = md.tables[name]
                conn.execute(delete(table).where(*[table.c[k] == v for k, v in zip(PK[name], key)]))
            for (name, key), (table, row) in current.items():
                old = self._snapshot.get((name, key))
                if old is None:
                    conn.execute(insert(table).values(row))
                elif old != row:
                    conn.execute(update(table).where(*[table.c[k] == v for k, v in zip(PK[name], key)]).values(row))
        self._snapshot = {k: row for k, (_, row) in current.items()}

    # ------------------------------------------------------------------ domain → rows
    def _rows(self):
        for i, u in enumerate(self.users.values()):
            yield users, dict(id=u.id, seq=i, display_name=u.display_name, role=str(u.role), username=u.username,
                              email=u.email, google_sub=u.google_sub)
        for s in self.sessions.values():
            yield sessions, dict(token=s.token, user_id=s.user_id, expires_at=_iso(s.expires_at))
        for i, p in enumerate(self.places.values()):
            yield places, dict(id=p.id, seq=i, name=p.name, category=p.category, lat=p.location.lat,
                               lon=p.location.lon, short_description=p.short_description, address=p.address,
                               owner_id=p.owner_id, external_id=p.external_id)
        for by_feature in self.states.values():
            for s in by_feature.values():
                yield states, dict(place_id=s.place_id, feature=str(s.feature), state=str(s.state),
                                   confidence=s.confidence, temporary=s.temporary, last_verified=_iso(s.last_verified),
                                   sources_count=s.sources_count, validation=str(s.validation),
                                   active_observation_id=s.active_observation_id)
        for i, o in enumerate(self.observations.values()):
            yield observations, dict(id=o.id, seq=i, place_id=o.place_id, feature=str(o.feature), value=str(o.value),
                                     source=str(o.source), author_id=o.author_id, created_at=_iso(o.created_at),
                                     temporary=o.temporary, comment=o.comment, evidence_ids=list(o.evidence_ids),
                                     votes=dict(o.votes), validation=str(o.validation), confidence=o.confidence,
                                     report_id=o.report_id)
        for i, r in enumerate(self.reports.values()):
            yield reports, dict(id=r.id, seq=i, place_id=r.place_id, author_id=r.author_id, element=str(r.element),
                                current_state=str(r.current_state), severity=str(r.severity), nature=str(r.nature),
                                description=r.description, created_at=_iso(r.created_at), photo_ids=list(r.photo_ids),
                                status=r.status, observation_ids=list(r.observation_ids))
        for i, p in enumerate(self.photos.values()):
            yield photos, dict(id=p.id, seq=i, path=p.path, url=p.url, original_name=p.original_name)
        for i, q in enumerate(self.queue.values()):
            yield queue, dict(id=q.id, seq=i, place_id=q.place_id, feature=str(q.feature),
                              created_at=_iso(q.created_at), observation_ids=list(q.observation_ids), type=q.type,
                              status=str(q.status), decision=q.decision)

    # ------------------------------------------------------------------ rows → domain
    def _load(self) -> None:
        with self.engine.connect() as conn:
            def rows(table):
                stmt = select(table).order_by(table.c.seq) if "seq" in table.c else select(table)
                return [r._mapping for r in conn.execute(stmt)]

            for r in rows(users):
                self.users[r["id"]] = User(r["id"], r["display_name"], Role(r["role"]), r["username"], r["email"],
                                           r["google_sub"])
            for r in rows(sessions):
                self.sessions[r["token"]] = Session(r["token"], r["user_id"], _dt(r["expires_at"]))
            for r in rows(places):
                self.places[r["id"]] = Place(r["id"], r["name"], r["category"], GeoPoint(r["lat"], r["lon"]),
                                             r["short_description"], r["address"], r["owner_id"], r["external_id"])
            for r in rows(states):
                s = FeatureStateRecord(r["place_id"], FeatureKey(r["feature"]), StateValue(r["state"]),
                                       r["confidence"], r["temporary"], _dt(r["last_verified"]), r["sources_count"],
                                       ValidationStatus(r["validation"]), r["active_observation_id"])
                self.states[s.place_id][s.feature] = s
            for r in rows(observations):
                self.observations[r["id"]] = Observation(
                    r["id"], r["place_id"], FeatureKey(r["feature"]), ObservationValue(r["value"]),
                    ObservationSource(r["source"]), r["author_id"], _dt(r["created_at"]), r["temporary"],
                    r["comment"], list(r["evidence_ids"]), dict(r["votes"]), ValidationStatus(r["validation"]),
                    r["confidence"], r["report_id"])
            for r in rows(reports):
                self.reports[r["id"]] = Report(
                    r["id"], r["place_id"], r["author_id"], FeatureKey(r["element"]), CurrentState(r["current_state"]),
                    Severity(r["severity"]), Nature(r["nature"]), r["description"], _dt(r["created_at"]),
                    list(r["photo_ids"]), r["status"], list(r["observation_ids"]))
            for r in rows(photos):
                self.photos[r["id"]] = Photo(r["id"], r["path"], r["url"], r["original_name"])
            for r in rows(queue):
                self.queue[r["id"]] = QueueItem(r["id"], r["place_id"], FeatureKey(r["feature"]), _dt(r["created_at"]),
                                                list(r["observation_ids"]), r["type"], QueueStatus(r["status"]),
                                                r["decision"])
        self._snapshot = {(t.name, tuple(row[k] for k in PK[t.name])): row for t, row in self._rows()}

