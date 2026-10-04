"""SQL persistence (SQLite or Postgres) via SQLAlchemy Core. Write-behind cache over InMemoryRepo:
load everything on start, `commit()` writes the diff since the last commit.
Single-process only (1 uvicorn worker). Datetimes as ISO strings (keeps tz), lists/dicts as JSON."""
import logging
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, Boolean, Column, Float, Integer, MetaData, String, Table, create_engine, delete, insert, \
    inspect, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.adapters.outbound.memory import InMemoryRepo
from app.application.ports import StaleData  # noqa: F401 — re-exported
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
    LoginToken,
    Notification,
    Question,
    FeatureStateRecord,
    GeoPoint,
    Observation,
    OwnershipRequest,
    Photo,
    Place,
    QueueItem,
    Report,
    Session,
    User,
)

log = logging.getLogger(__name__)
md = MetaData()

meta = Table("meta", md, Column("key", String, primary_key=True), Column("value", Integer))  # F29 data_version
VERSION_KEY = "data_version"
users = Table("users", md, Column("id", String, primary_key=True), Column("seq", Integer),
              Column("display_name", String), Column("role", String), Column("username", String),
              Column("email", String), Column("google_sub", String), Column("favorites", JSON),
              Column("needs", JSON), Column("pref_features", JSON))
sessions = Table("sessions", md, Column("token", String, primary_key=True), Column("user_id", String),
                 Column("expires_at", String))
login_tokens = Table("login_tokens", md, Column("token_hash", String, primary_key=True), Column("email", String),
                     Column("created_at", String), Column("expires_at", String), Column("used", Boolean))
questions = Table("questions", md, Column("id", String, primary_key=True), Column("seq", Integer),
                  Column("place_id", String), Column("author_id", String), Column("text", String),
                  Column("created_at", String), Column("feature", String), Column("status", String),
                  Column("answer_text", String), Column("answered_by", String), Column("answered_at", String),
                  Column("outcome", String))
notifications = Table("notifications", md, Column("id", String, primary_key=True), Column("seq", Integer),
                      Column("user_id", String), Column("kind", String), Column("text", String),
                      Column("created_at", String), Column("place_id", String), Column("ref_id", String),
                      Column("read", Boolean))
places = Table("places", md, Column("id", String, primary_key=True), Column("seq", Integer), Column("name", String),
               Column("category", String), Column("lat", Float), Column("lon", Float),
               Column("short_description", String), Column("address", String), Column("owner_id", String),
               Column("external_id", String), Column("opening_hours", JSON), Column("contact", JSON),
               Column("photo_ids", JSON), Column("place_type", String), Column("kind", String))
states = Table("feature_states", md, Column("place_id", String, primary_key=True),
               Column("feature", String, primary_key=True), Column("state", String), Column("confidence", Float),
               Column("temporary", Boolean), Column("last_verified", String), Column("sources_count", Integer),
               Column("validation", String), Column("active_observation_id", String))
observations = Table("observations", md, Column("id", String, primary_key=True), Column("seq", Integer),
                     Column("place_id", String, index=True), Column("feature", String), Column("value", String),
                     Column("source", String), Column("author_id", String), Column("created_at", String),
                     Column("temporary", Boolean), Column("comment", String), Column("evidence_ids", JSON),
                     Column("votes", JSON), Column("validation", String), Column("confidence", Float),
                     Column("report_id", String), Column("flag_reason", String), Column("valid_until", String))
reports = Table("reports", md, Column("id", String, primary_key=True), Column("seq", Integer),
                Column("place_id", String), Column("author_id", String), Column("element", String),
                Column("current_state", String), Column("severity", String), Column("nature", String),
                Column("description", String), Column("created_at", String), Column("photo_ids", JSON),
                Column("status", String), Column("observation_ids", JSON), Column("replies", JSON),
                Column("owner_status", String))
photos = Table("photos", md, Column("id", String, primary_key=True), Column("seq", Integer), Column("path", String),
               Column("url", String), Column("original_name", String), Column("place_id", String),
               Column("element", String), Column("current_state", String))
queue = Table("queue_items", md, Column("id", String, primary_key=True), Column("seq", Integer),
              Column("place_id", String), Column("feature", String), Column("created_at", String),
              Column("observation_ids", JSON), Column("type", String), Column("status", String),
              Column("decision", String), Column("resolved_at", String), Column("comments", JSON))
ownership = Table("ownership_requests", md, Column("id", String, primary_key=True), Column("seq", Integer),
                  Column("place_id", String), Column("user_id", String), Column("justification", String),
                  Column("created_at", String), Column("status", String), Column("decided_at", String))

PK = {t.name: [c.name for c in t.primary_key.columns] for t in md.sorted_tables}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _s(v) -> str | None:
    return None if v is None else str(v)


def _e(enum_cls, v):
    return None if v is None else enum_cls(v)


class SqlRepo(InMemoryRepo):
    def __init__(self, url: str, connect_retries: int = 15, retry_pause_s: float = 2.0):
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, pool_pre_ping=True)
        for attempt in range(1, connect_retries + 1):  # Postgres in docker may still be booting
            try:
                md.create_all(self.engine)
                self._add_missing_columns()
                break
            except OperationalError:
                if attempt == connect_retries:
                    raise
                log.warning("database not ready (attempt %s/%s), retrying…", attempt, connect_retries)
                time.sleep(retry_pause_s)
        self._ensure_version_row()
        super().__init__()
        self._snapshot: dict[tuple[str, tuple], dict] = {}
        self.version = 0
        self._load()

    def _ensure_version_row(self) -> None:
        try:
            with self.engine.begin() as conn:
                if conn.execute(select(meta.c.value).where(meta.c.key == VERSION_KEY)).first() is None:
                    conn.execute(insert(meta).values(key=VERSION_KEY, value=0))
        except IntegrityError:
            pass  # another worker created it at the same moment

    def _read_version(self, conn) -> int:
        return conn.execute(select(meta.c.value).where(meta.c.key == VERSION_KEY)).scalar() or 0

    def reload_if_stale(self) -> bool:
        """F29: one single-row read per request; reload the whole cache when another worker committed."""
        with self.engine.connect() as conn:
            if self._read_version(conn) == self.version:
                return False
        self._reload()
        return True

    def _reload(self) -> None:
        self.clear()
        self._load()

    def _add_missing_columns(self) -> None:
        """Lightweight schema evolution: new nullable columns appear in DBs created by older versions."""
        existing = inspect(self.engine)
        quote = self.engine.dialect.identifier_preparer.quote
        with self.engine.begin() as conn:
            for table in md.sorted_tables:
                have = {c["name"] for c in existing.get_columns(table.name)}
                for col in table.columns:
                    if col.name not in have:
                        ddl = col.type.compile(dialect=self.engine.dialect)
                        conn.execute(text(f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(col.name)} {ddl}"))
                        log.warning("schema: added column %s.%s", table.name, col.name)

    # ------------------------------------------------------------------ port extras
    def commit(self) -> None:
        """Write the diff since the last load/commit. Optimistic lock: data_version must still be ours."""
        current = {(t.name, tuple(row[k] for k in PK[t.name])): (t, row) for t, row in self._rows()}
        if current.keys() == self._snapshot.keys() and all(self._snapshot[k] == row for k, (_, row) in current.items()):
            return  # nothing changed → no version bump, never stale
        try:
            self._write(current)
        except StaleData:
            self._reload()  # drop this worker's unsaved changes, take the other worker's data
            raise
        self.version += 1
        self._snapshot = {k: row for k, (_, row) in current.items()}

    def _write(self, current) -> None:
        with self.engine.begin() as conn:
            bumped = conn.execute(update(meta).where(meta.c.key == VERSION_KEY, meta.c.value == self.version)
                                  .values(value=self.version + 1))
            if bumped.rowcount != 1:
                raise StaleData("concurrent update by another worker — retry")
            for name, key in self._snapshot.keys() - current.keys():
                table = md.tables[name]
                conn.execute(delete(table).where(*[table.c[k] == v for k, v in zip(PK[name], key)]))
            for (name, key), (table, row) in current.items():
                old = self._snapshot.get((name, key))
                if old is None:
                    conn.execute(insert(table).values(row))
                elif old != row:
                    conn.execute(update(table).where(*[table.c[k] == v for k, v in zip(PK[name], key)]).values(row))

    # ------------------------------------------------------------------ domain → rows
    def _rows(self):
        for i, u in enumerate(self.users.values()):
            yield users, dict(id=u.id, seq=i, display_name=u.display_name, role=str(u.role), username=u.username,
                              email=u.email, google_sub=u.google_sub, favorites=list(u.favorite_place_ids),
                              needs=list(u.needs), pref_features=list(u.pref_features))
        for s in self.sessions.values():
            yield sessions, dict(token=s.token, user_id=s.user_id, expires_at=_iso(s.expires_at))
        for i, q in enumerate(self.questions.values()):
            yield questions, dict(id=q.id, seq=i, place_id=q.place_id, author_id=q.author_id, text=q.text,
                                  created_at=_iso(q.created_at), feature=_s(q.feature), status=q.status,
                                  answer_text=q.answer_text, answered_by=q.answered_by,
                                  answered_at=_iso(q.answered_at), outcome=q.outcome)
        for i, n in enumerate(self.notifications.values()):
            yield notifications, dict(id=n.id, seq=i, user_id=n.user_id, kind=n.kind, text=n.text,
                                      created_at=_iso(n.created_at), place_id=n.place_id, ref_id=n.ref_id,
                                      read=n.read)
        for t in self.login_tokens.values():
            yield login_tokens, dict(token_hash=t.token_hash, email=t.email, created_at=_iso(t.created_at),
                                     expires_at=_iso(t.expires_at), used=t.used)
        for i, p in enumerate(self.places.values()):
            yield places, dict(id=p.id, seq=i, name=p.name, category=p.category, lat=p.location.lat,
                               lon=p.location.lon, short_description=p.short_description, address=p.address,
                               owner_id=p.owner_id, external_id=p.external_id, opening_hours=list(p.opening_hours),
                               contact=dict(p.contact), photo_ids=list(p.photo_ids), place_type=p.place_type,
                               kind=p.kind)
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
                                     report_id=o.report_id, flag_reason=o.flag_reason, valid_until=_iso(o.valid_until))
        for i, r in enumerate(self.reports.values()):
            yield reports, dict(id=r.id, seq=i, place_id=r.place_id, author_id=r.author_id, element=_s(r.element),
                                current_state=_s(r.current_state), severity=_s(r.severity), nature=_s(r.nature),
                                description=r.description, created_at=_iso(r.created_at), photo_ids=list(r.photo_ids),
                                status=r.status, observation_ids=list(r.observation_ids), replies=list(r.replies),
                                owner_status=r.owner_status)
        for i, p in enumerate(self.photos.values()):
            yield photos, dict(id=p.id, seq=i, path=p.path, url=p.url, original_name=p.original_name,
                               place_id=p.place_id, element=p.element, current_state=p.current_state)
        for i, q in enumerate(self.queue.values()):
            yield queue, dict(id=q.id, seq=i, place_id=q.place_id, feature=_s(q.feature),
                              created_at=_iso(q.created_at), observation_ids=list(q.observation_ids), type=q.type,
                              status=str(q.status), decision=q.decision, resolved_at=_iso(q.resolved_at),
                              comments=list(q.comments))
        for i, r in enumerate(self.ownership_requests.values()):
            yield ownership, dict(id=r.id, seq=i, place_id=r.place_id, user_id=r.user_id,
                                  justification=r.justification, created_at=_iso(r.created_at), status=r.status,
                                  decided_at=_iso(r.decided_at))

    # ------------------------------------------------------------------ rows → domain
    def _load(self) -> None:
        with self.engine.connect() as conn:
            self.version = self._read_version(conn)
            def rows(table):
                stmt = select(table).order_by(table.c.seq) if "seq" in table.c else select(table)
                return [r._mapping for r in conn.execute(stmt)]

            for r in rows(users):
                self.users[r["id"]] = User(r["id"], r["display_name"], Role(r["role"]), r["username"], r["email"],
                                           r["google_sub"], list(r["favorites"] or []), list(r["needs"] or []),
                                           list(r["pref_features"] or []))
            for r in rows(sessions):
                self.sessions[r["token"]] = Session(r["token"], r["user_id"], _dt(r["expires_at"]))
            for r in rows(questions):
                self.questions[r["id"]] = Question(
                    r["id"], r["place_id"], r["author_id"], r["text"], _dt(r["created_at"]),
                    _e(FeatureKey, r["feature"]), r["status"], r["answer_text"], r["answered_by"],
                    _dt(r["answered_at"]), r["outcome"])
            for r in rows(notifications):
                self.notifications[r["id"]] = Notification(r["id"], r["user_id"], r["kind"], r["text"],
                                                           _dt(r["created_at"]), r["place_id"], r["ref_id"],
                                                           bool(r["read"]))
            for r in rows(login_tokens):
                self.login_tokens[r["token_hash"]] = LoginToken(r["token_hash"], r["email"], _dt(r["created_at"]),
                                                                _dt(r["expires_at"]), bool(r["used"]))
            for r in rows(places):
                self.places[r["id"]] = Place(r["id"], r["name"], r["category"], GeoPoint(r["lat"], r["lon"]),
                                             r["short_description"], r["address"], r["owner_id"], r["external_id"],
                                             list(r["opening_hours"] or []), dict(r["contact"] or {}),
                                             list(r["photo_ids"] or []), r["place_type"] or "venue",
                                             r.get("kind") or "")
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
                    r["confidence"], r["report_id"], r["flag_reason"], _dt(r["valid_until"]))
            for r in rows(reports):
                self.reports[r["id"]] = Report(
                    r["id"], r["place_id"], r["author_id"], _e(FeatureKey, r["element"]),
                    _e(CurrentState, r["current_state"]), _e(Severity, r["severity"]), _e(Nature, r["nature"]),
                    r["description"], _dt(r["created_at"]),
                    list(r["photo_ids"]), r["status"], list(r["observation_ids"]), list(r["replies"] or []),
                    r["owner_status"])
            for r in rows(photos):
                self.photos[r["id"]] = Photo(r["id"], r["path"], r["url"], r["original_name"],
                                             r.get("place_id"), r.get("element"), r.get("current_state"))
            for r in rows(queue):
                self.queue[r["id"]] = QueueItem(r["id"], r["place_id"], _e(FeatureKey, r["feature"]), _dt(r["created_at"]),
                                                list(r["observation_ids"]), r["type"], QueueStatus(r["status"]),
                                                r["decision"], _dt(r["resolved_at"]), list(r["comments"] or []))
            for r in rows(ownership):
                self.ownership_requests[r["id"]] = OwnershipRequest(
                    r["id"], r["place_id"], r["user_id"], r["justification"], _dt(r["created_at"]), r["status"],
                    _dt(r["decided_at"]))
        self._snapshot = {(t.name, tuple(row[k] for k in PK[t.name])): row for t, row in self._rows()}

