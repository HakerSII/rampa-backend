"""All MVP use cases (application layer). Depends only on domain + ports."""
import logging
import hashlib
import math
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
import csv
import io
import re
from datetime import datetime, timedelta

from app.application.ports import (
    Clock,
    FileStorage,
    IdentityVerifier,
    IdGenerator,
    Geocoder,
    OsmSource,
    Mailer,
    QueryInterpreter,
    WalkingRouter,
    Repo,
    VisionAnalyzer,
)
from app.domain import check as domain_check, osm as domain_osm, suggestions, trust, validation
from app.domain.geo import haversine_m, in_bbox, parse_bbox
from app.domain import recommend as recommend_domain
from app.domain.city import City
from app.domain.text import clean_text, is_email, is_http_url, is_phone
from app.domain.recommend import Intent, Recommendation
from app.domain.route import RouteResult, plan_route
from app.domain.text_parse import TextSuggestion, parse_text
from app.domain.history import HistoryEvent, build_history
from app.domain.stats import AdminStats, compute_stats
from app.domain.verification import Verification, activity_type, summarize
from app.domain.enums import (
    FEATURE_GROUP,
    LABELS_PL,
    CurrentState,
    DecisionAction,
    FeatureKey,
    Nature,
    NeedsProfile,
    ObservationSource,
    PlaceType,
    ObservationValue,
    QueueStatus,
    Role,
    Severity,
    StateValue,
    ValidationStatus,
)
from app.domain.errors import (
    RateLimited,
    ConflictError,
    FileTooLarge,
    Forbidden,
    NotARealPlace,
    NotFound,
    PhotoMismatch,
    Unauthorized,
    ValidationFailed,
)
from app.domain.model import (
    CheckResult,
    FeatureStateRecord,
    GeocodeHit,
    LoginToken,
    Notification,
    Question,
    GeoPoint,
    ImageAnalysis,
    Observation,
    OwnershipRequest,
    Photo,
    Place,
    QueueItem,
    Report,
    Session,
    User,
)
from app.seed import OSM_AUTHOR_ID, SEED_AUTHOR_ID, load_seed

DEMO_TOKEN_PREFIX = "demo-"
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTOS = 5
MAX_OWNER_BATCH = 10
MAX_DESCRIPTION = 1000
MAX_PLACE_NAME = 120
MAX_DISPLAY_NAME = 60
ANONYMOUS_NAME = "Anonim"
IMAGE_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg"}


SORTS = (None, "nearest", "name", "recently_verified", "best_match")
MAX_NEEDS = 10
DEFAULT_RADIUS_M = 2000


@dataclass(slots=True)
class PlaceQuery:
    features: list[FeatureKey] | None = None
    category: str | None = None
    q: str | None = None
    near: GeoPoint | None = None
    radius_m: int | None = None
    bbox: str | None = None
    sort: str | None = None
    page: int = 1
    page_size: int = 20
    place_types: list[str] | None = None
    profiles: list[NeedsProfile] | None = None  # F31 best_match


@dataclass(slots=True)
class PlaceResults:
    items: list[tuple[Place, int | None]]  # (place, distance in m or None)
    total: int
    page: int
    page_size: int


@dataclass(slots=True)
class CategoryCount:
    key: str
    count: int


@dataclass(slots=True)
class OwnerProfile:
    id: str
    display_name: str
    email: str | None
    role: Role
    verified: bool
    places: int


@dataclass(slots=True)
class OwnerStats:
    managed_places: int
    avg_confidence: float
    reports_30d: int
    updates_30d: int
    open_conflicts: int


@dataclass(slots=True)
class OwnerPlaceStats:
    observations: int
    by_source: dict[str, int]
    votes_up: int
    votes_down: int
    open_conflicts: int
    last_verified: datetime | None
    confidence: float


@dataclass(slots=True)
class ActivityCell:
    lat: float
    lon: float
    observations: int
    reports: int


@dataclass(slots=True)
class TrendDay:
    day: str
    observations: int
    reports: int
    questions: int
    queue_items: int


@dataclass(slots=True)
class CategoryCoverage:
    category: str
    places: int
    with_data: int
    avg_known_features: float


@dataclass(slots=True)
class Coverage:
    categories: list[CategoryCoverage]
    most_missing: list[tuple[FeatureKey, int]]


@dataclass(slots=True)
class NeedsStats:
    by_feature: list[tuple[FeatureKey, int]]  # most asked first
    open: int
    answered: int
    without_feature: int


@dataclass(slots=True)
class Reminder:
    place_id: str
    kind: str  # missing_data | stale_data | conflict | unanswered_report
    text: str
    priority: str  # high | normal
    feature: FeatureKey | None = None


@dataclass(slots=True)
class OwnerSuggestion:
    place_id: str
    feature: FeatureKey
    text: str


@dataclass(slots=True)
class CsvImportResult:
    imported: int
    errors: list[dict]


@dataclass(slots=True)
class PlaceConfidence:
    overall: float
    by_group: dict[str, float]
    note: str


@dataclass(slots=True)
class RecommendResult:
    intent: Intent
    items: list[Recommendation]
    model: str
    note: str


@dataclass(slots=True)
class ImportResult:
    source: str
    points: int = 0
    places_created: int = 0
    places_matched: int = 0
    observations: int = 0
    skipped_unnamed: int = 0
    skipped_no_data: int = 0


@dataclass(slots=True)
class ImageTagsResult:
    analysis: ImageAnalysis
    tags: list[suggestions.Tag]
    detected: str
    suggested: suggestions.Suggested | None
    model: str


REPORT_VALUE = {CurrentState.WORKS: ObservationValue.YES, CurrentState.PARTIALLY_WORKS: ObservationValue.PARTIAL,
                CurrentState.NOT_WORKING: ObservationValue.NO}


log = logging.getLogger(__name__)


EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")
MAX_EMAIL = 254
EMAIL_TOKEN_TTL = timedelta(minutes=15)
EMAIL_MAX_REQUESTS = 3


def _seq(entity_id: str) -> int:
    tail = entity_id.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _enum(enum_cls, value, field: str):
    try:
        return enum_cls(value)
    except ValueError as e:
        raise ValidationFailed(f"invalid {field}: {value}") from e


class UseCases:
    def __init__(self, repo: Repo, clock: Clock, ids: IdGenerator, storage: FileStorage,
                 verifier: IdentityVerifier | None, *, auth_mode: str = "demo",
                 admin_emails: list[str] | None = None, session_ttl_hours: int = 24,
                 anonymous_auth: bool = True, anonymous_ttl_days: int = 365,
                 vision: VisionAnalyzer | None = None, osm: OsmSource | None = None,
                 geocoder: Geocoder | None = None, osm_live: OsmSource | None = None,
                 router: WalkingRouter | None = None, recommender: QueryInterpreter | None = None,
                 mailer: Mailer | None = None, email_login: bool = True, email_dev_token: bool = False,
                 email_link_url: str = "", city: City | None = None):
        self.repo = repo
        self.clock = clock
        self.ids = ids
        self.storage = storage
        self.verifier = verifier
        self.auth_mode = auth_mode
        self.admin_emails = admin_emails or []
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.anonymous_auth = anonymous_auth
        self.anonymous_ttl = timedelta(days=anonymous_ttl_days)
        self.vision = vision
        self.osm = osm
        self.geocoder = geocoder
        self.osm_live = osm_live
        self.router = router
        self.recommender = recommender
        self.mailer = mailer
        self.email_login = email_login
        self.email_dev_token = email_dev_token  # demo + console mailer only: code returned in the response
        self.email_link_url = email_link_url
        self.city = city or recommend_domain.default_city()

    # ------------------------------------------------------------------ multi-worker (F29)
    def sync(self, force: bool = False) -> bool:
        """Before each request: pick up other workers' commits; continue id sequences after a reload."""
        reloaded = self.repo.reload_if_stale()
        if reloaded or force:
            for existing_id in self.repo.all_ids():
                self.ids.observe(existing_id)
        return reloaded

    # ------------------------------------------------------------------ demo data
    def load_seed(self) -> None:
        load_seed(self.repo, self.clock, self.ids, self.recompute)

    def reset_demo(self, admin: User) -> None:
        self._require_admin(admin)
        self.repo.clear()
        self.ids.reset()
        self.load_seed()

    # ------------------------------------------------------------------ auth
    def login_demo(self, username: str) -> tuple[str, User]:
        if self.auth_mode != "demo":
            raise NotFound("demo login disabled")
        user = self.repo.find_user_by_username(username)
        if user is None:
            raise Unauthorized(f"unknown demo user: {username}")
        return DEMO_TOKEN_PREFIX + username, user

    async def login_with_google(self, id_token: str) -> tuple[str, User]:
        if self.auth_mode != "google" or self.verifier is None:
            raise NotFound("Google login disabled (AUTH_MODE != google)")
        identity = await self.verifier.verify(id_token)
        if not identity.email_verified:
            raise Unauthorized("Google e-mail not verified")
        role = Role.ADMIN if identity.email.lower() in self.admin_emails else Role.USER
        user = self.repo.find_user_by_google_sub(identity.sub) or self.repo.find_user_by_email(identity.email)
        if user is not None:
            user.google_sub = identity.sub  # same verified e-mail as an e-mail login (F33) → same account
        if user is None:
            user = User(self.ids.new("usr"), identity.name or identity.email, role,
                        email=identity.email, google_sub=identity.sub)
            self.repo.add_user(user)
        else:
            user.email, user.display_name, user.role = identity.email, identity.name or user.display_name, role
        return self._new_session(user), user

    def login_anonymous(self, display_name: str | None = None) -> tuple[str, User]:
        """Device identity for the map front end (F12): a fresh `user` with a long-lived session.
        Works in every auth mode, so votes are per device even without Google. One call = one user;
        the front end stores the token and reuses it."""
        if not self.anonymous_auth:
            raise NotFound("anonymous login disabled (ANONYMOUS_AUTH=false)")
        name = (display_name or "").strip()[:MAX_DISPLAY_NAME] or ANONYMOUS_NAME
        user = User(self.ids.new("usr"), name, Role.USER)
        self.repo.add_user(user)
        return self._new_session(user, self.anonymous_ttl), user

    # ------------------------------------------------------------------ e-mail login (F33)
    async def request_email_login(self, email: str) -> str | None:
        """Send a one-time code (15 min, single use). Same answer for known and unknown addresses.
        Returns the code only in demo + console mode (e2e / stage), never with a real mailer."""
        if not self.email_login or self.mailer is None:
            raise NotFound("e-mail login disabled (EMAIL_LOGIN=false)")
        email = (email or "").strip().lower()
        if len(email) > MAX_EMAIL or not EMAIL_RE.fullmatch(email):
            raise ValidationFailed("invalid e-mail address")
        now = self.clock.now()
        recent = [t for t in self.repo.list_login_tokens(email) if t.created_at > now - EMAIL_TOKEN_TTL]
        if len(recent) >= EMAIL_MAX_REQUESTS:
            wait = int((min(t.created_at for t in recent) + EMAIL_TOKEN_TTL - now).total_seconds()) + 1
            raise RateLimited("too many login e-mails for this address, try later", retry_after=wait)
        code = secrets.token_urlsafe(24)
        self.repo.add_login_token(LoginToken(_hash(code), email, now, now + EMAIL_TOKEN_TTL))
        link = f"{self.email_link_url}?token={code}" if self.email_link_url else ""
        text = (f"Kod logowania: {code}\n\n" + (f"Albo kliknij: {link}\n\n" if link else "")
                + "Kod jest ważny 15 min i działa jeden raz. Jeśli to nie Ty — zignoruj tę wiadomość.")
        await self.mailer.send(email, "Kraków bez barier — logowanie", text)
        return code if self.email_dev_token else None

    def verify_email_login(self, code: str) -> tuple[str, User]:
        token = self.repo.get_login_token(_hash((code or "").strip()))
        if token is None or token.used or token.expires_at <= self.clock.now():
            raise Unauthorized("login code invalid, used or expired")
        token.used = True
        user = self.repo.find_user_by_email(token.email)
        role = Role.ADMIN if token.email in self.admin_emails else Role.USER
        if user is None:
            user = User(self.ids.new("usr"), token.email.split("@")[0][:MAX_DISPLAY_NAME], role, email=token.email)
            self.repo.add_user(user)
        elif role == Role.ADMIN:
            user.role = Role.ADMIN
        return self._new_session(user), user

    def logout(self, token: str | None) -> None:
        if token:
            self.repo.delete_session(token)

    def current_user(self, token: str | None) -> User | None:
        """None = guest. Demo tokens are stateless, so they survive demo reset."""
        if not token:
            return None
        if self.auth_mode == "demo" and token.startswith(DEMO_TOKEN_PREFIX):
            return self.repo.find_user_by_username(token.removeprefix(DEMO_TOKEN_PREFIX))
        session = self.repo.get_session(token)
        if session is None or session.expires_at <= self.clock.now():
            return None
        return self.repo.get_user(session.user_id)

    def _new_session(self, user: User, ttl: timedelta | None = None) -> str:
        token = secrets.token_urlsafe(32)
        self.repo.add_session(Session(token, user.id, self.clock.now() + (ttl or self.session_ttl)))
        return token

    @staticmethod
    def _require_admin(user: User | None) -> None:
        if user is None:
            raise Unauthorized("login required")
        if user.role != Role.ADMIN:
            raise Forbidden("admin role required")

    # ------------------------------------------------------------------ places (F2)
    def search_places(self, features: list[FeatureKey] | None = None, category: str | None = None,
                      q: str | None = None) -> list[Place]:
        result = []
        for place in self.repo.list_places():
            if category and place.category != category:
                continue
            if q and q.lower() not in place.name.lower():
                continue
            self._refresh_expired(place.id)
            states = self.repo.states_for(place.id)
            if features and not all(f in states and states[f].state == StateValue.YES for f in features):
                continue
            result.append(place)
        return result

    def find_places(self, query: PlaceQuery) -> PlaceResults:
        """Search + distance/radius/bbox + sort + pagination (F17)."""
        if not (query.page >= 1 and 1 <= query.page_size <= 100):
            raise ValidationFailed("page >= 1, page_size 1..100")
        matches = self._filter_and_sort(query)
        start = (query.page - 1) * query.page_size
        return PlaceResults(matches[start:start + query.page_size], len(matches), query.page, query.page_size)

    def map_markers(self, query: PlaceQuery) -> list[tuple[Place, str]]:
        """All matches (no pagination) with a wheelchair marker for the map."""
        marker = {"yes": "accessible", "partial": "partial", "no": "inaccessible", "unknown": "unknown"}
        return [(p, marker[str(self.check_place(p.id, NeedsProfile.WHEELCHAIR).answer)])
                for p, _ in self._filter_and_sort(query)]

    def _filter_and_sort(self, query: PlaceQuery) -> list[tuple[Place, int | None]]:
        if query.sort not in SORTS:
            raise ValidationFailed(f"sort must be one of: nearest, name, recently_verified, best_match "
                                   f"(got {query.sort})")
        if query.sort == "best_match" and not query.profiles:
            raise ValidationFailed("sort=best_match needs profile= or a stored needs profile (PUT /me/profile)")
        if query.sort == "nearest" and query.near is None:
            raise ValidationFailed("sort=nearest needs lat and lon")
        try:
            bbox = parse_bbox(query.bbox) if query.bbox else None
        except ValueError as e:
            raise ValidationFailed(str(e)) from e

        types = set(query.place_types or [])
        for t in types:
            _enum(PlaceType, t, "place_type")
        items = []
        for p in self.search_places(query.features, query.category, query.q):
            if types and p.place_type not in types:
                continue
            distance = round(haversine_m(query.near, p.location)) if query.near else None
            if query.near and distance > (query.radius_m or DEFAULT_RADIUS_M):
                continue
            if bbox and not in_bbox(p.location, bbox):
                continue
            items.append((p, distance))

        sort = query.sort or ("nearest" if query.near else None)
        if sort == "nearest":
            items.sort(key=lambda t: t[1])
        elif sort == "name":
            items.sort(key=lambda t: t[0].name.casefold())
        elif sort == "best_match":
            score = {p.id: recommend_domain.evaluate(p.id, self.repo.states_for(p.id), query.profiles, [])
                     for p, _ in items}
            items.sort(key=lambda t: (score[t[0].id][0] == "no", -score[t[0].id][1],
                                      t[1] if t[1] is not None else 0, t[0].name.casefold()))
        elif sort == "recently_verified":
            last = {p.id: self.verification_for(p.id).last_verified for p, _ in items}
            items.sort(key=lambda t: (last[t[0].id] is not None, last[t[0].id] or 0), reverse=True)
        return items

    def list_categories(self) -> list[CategoryCount]:
        counts: dict[str, int] = {}
        for p in self.repo.list_places():
            counts[p.category] = counts.get(p.category, 0) + 1
        return [CategoryCount(k, v) for k, v in counts.items()]

    def geocode(self, q: str) -> list[GeocodeHit]:
        """Search-box suggestions from the local place index (offline; no Nominatim)."""
        needle = (q or "").strip().casefold()
        if len(needle) < 2:
            raise ValidationFailed("q: at least 2 characters")
        hits = [GeocodeHit(f"{p.name}, {p.address}" if p.address else p.name, p.id, p.location)
                for p in self.repo.list_places()
                if needle in p.name.casefold() or needle in (p.address or "").casefold()]
        return hits[:10]

    async def geocode_live(self, q: str) -> list[GeocodeHit]:
        """F27: local places first (they have data), then live geocoder hits; geocoder failure → local only."""
        local = self.geocode(q)
        if self.geocoder is None:
            return local
        try:
            external = await self.geocoder.search(q.strip())
        except Exception as e:  # noqa: BLE001 — network / quota / parse → offline answer
            log.warning("geocoder failed (%s) → local only", e)
            return local
        places = self.repo.list_places()
        fresh = [h for h in external
                 if not any(haversine_m(p.location, h.location) <= domain_osm.MATCH_RADIUS_M for p in places)]
        return (local + fresh)[:10]

    def get_place(self, place_id: str) -> Place:
        place = self.repo.get_place(place_id)
        if place is None:
            raise NotFound(f"place not found: {place_id}")
        return place

    def get_accessibility(self, place_id: str) -> dict[FeatureKey, FeatureStateRecord]:
        """All MVP features; missing = unknown."""
        self.get_place(place_id)
        self._refresh_expired(place_id)
        states = self.repo.states_for(place_id)
        return {f: states.get(f) or FeatureStateRecord(place_id, f, StateValue.UNKNOWN) for f in FeatureKey}

    def check_place(self, place_id: str, profile: NeedsProfile) -> CheckResult:
        states = self.get_accessibility(place_id)
        issues = [o for o in self.repo.list_observations(place_id)
                  if o.temporary and o.value == ObservationValue.NO
                  and validation.is_active(o)
                  and states[o.feature].active_observation_id == o.id]
        return domain_check.check_place(place_id, states, profile, issues)

    # ------------------------------------------------------------------ similar + routes (F20)
    SIMILAR_RADIUS_M = 3000

    def similar_places(self, place_id: str, limit: int = 5) -> list[tuple[Place, int]]:
        """Other places within 3 km: same category first, then nearest."""
        if not 1 <= limit <= 20:
            raise ValidationFailed("limit: 1..20")
        place = self.get_place(place_id)
        others = [(p, round(haversine_m(place.location, p.location))) for p in self.repo.list_places()
                  if p.id != place.id]
        near = [t for t in others if t[1] <= self.SIMILAR_RADIUS_M]
        near.sort(key=lambda t: (t[0].category != place.category, t[1]))
        return near[:limit]

    def accessible_route(self, origin: str, destination: str, profile: NeedsProfile) -> RouteResult:
        a, b = self._resolve_point(origin), self._resolve_point(destination)
        places = [(p, self.repo.states_for(p.id)) for p in self.repo.list_places()]
        return plan_route(a, b, profile, places)

    async def accessible_route_live(self, origin: str, destination: str, profile: NeedsProfile) -> RouteResult:
        """F28: walking path from the routing engine; failure / no route → straight-line heuristic."""
        a, b = self._resolve_point(origin), self._resolve_point(destination)
        path = None
        if self.router is not None:
            try:
                path = await self.router.walk(a, b)
            except Exception as e:  # noqa: BLE001 — network / timeout / parse → straight line
                log.warning("router failed (%s) → straight line", e)
        places = [(p, self.repo.states_for(p.id)) for p in self.repo.list_places()]
        return plan_route(a, b, profile, places, path)

    async def recommend(self, user: User | None, query: str, profile: NeedsProfile | None = None,
                        lat: float | None = None, lon: float | None = None, limit: int = 5) -> RecommendResult:
        """F30: query → needs/filters (model or rules) → ranking + reasons + missing from the DB only."""
        query = (query or "").strip()
        if not 1 <= len(query) <= recommend_domain.MAX_QUERY:
            raise ValidationFailed(f"query must have 1..{recommend_domain.MAX_QUERY} characters")
        if not 1 <= limit <= 20:
            raise ValidationFailed("limit 1..20")
        intent, model = None, "rules"
        if self.recommender is not None:
            try:
                intent, model = await self.recommender.interpret(query), self.recommender.model
            except Exception as e:  # noqa: BLE001 — network / quota / bad answer → rules
                log.warning("recommender failed (%s) → rules", e)
        if intent is None:
            intent = recommend_domain.interpret_rules(query, self.city)
        recognised = not intent.empty
        stored_needs, stored_features = self.get_needs_profile(user) if user else ([], [])
        for p in [*stored_needs, *([profile] if profile else [])]:
            if p not in intent.profiles:
                intent.profiles.append(p)
        for f in stored_features:
            if f not in intent.features:
                intent.features.append(f)
        origin = GeoPoint(lat, lon) if lat is not None and lon is not None else None
        places = []
        for p in self.repo.list_places():
            self._refresh_expired(p.id)
            states = self.repo.states_for(p.id)
            sources = {o.id: str(o.source) for o in self.repo.list_observations(p.id)}
            places.append((p, states, sources))
        items = recommend_domain.rank(places, intent, origin, self.clock.now(), limit, self.city)
        note = ("Wyniki tylko z bazy; brakujące lub stare dane są w `missing`." if recognised else
                "Nie rozpoznano potrzeb ani rodzaju miejsca — pokazuję miejsca z danymi; doprecyzuj zapytanie.")
        return RecommendResult(intent, items, model, note)

    def _resolve_point(self, raw: str) -> GeoPoint:
        """Place id or 'lat,lon'."""
        place = self.repo.get_place(raw)
        if place:
            return place.location
        if "," not in raw:
            raise NotFound(f"unknown place or point: {raw}")
        try:
            lat, lon = (float(x) for x in raw.split(","))
        except ValueError as e:
            raise ValidationFailed(f"point must be 'lat,lon' or a place id: {raw}") from e
        return GeoPoint(lat, lon)

    def place_match(self, place_id: str, profiles: list[NeedsProfile]) -> str:
        return recommend_domain.evaluate(place_id, self.repo.states_for(place_id), profiles, [])[0]

    # ------------------------------------------------------------------ questions to the owner (F34)
    def ask_question(self, user: User | None, place_id: str, text: str, feature: str | None = None) -> Question:
        self._require_user(user)
        self.get_place(place_id)
        text = (text or "").strip()
        if not 1 <= len(text) <= MAX_DESCRIPTION:
            raise ValidationFailed(f"text must have 1..{MAX_DESCRIPTION} characters")
        q = Question(self.ids.new("qst"), place_id, user.id, text, self.clock.now(),
                     _enum(FeatureKey, feature, "feature") if feature else None)
        self.repo.add_question(q)
        return q

    def place_questions(self, place_id: str) -> list[Question]:
        self.get_place(place_id)
        return sorted((q for q in self.repo.list_questions() if q.place_id == place_id),
                      key=lambda q: q.created_at, reverse=True)

    def owner_questions(self, user: User | None, status: str = "open") -> list[Question]:
        """Owner: questions on own places; admin: all."""
        self._require_user(user)
        if status not in ("open", "answered", "all"):
            raise ValidationFailed("status: open|answered|all")
        places = self._managed_place_ids(user)
        return [q for q in self.repo.list_questions()
                if q.place_id in places and (status == "all" or q.status == status)]

    def answer_question(self, user: User | None, question_id: str, text: str, value: str | None = None,
                        planned: bool = False) -> Question:
        """Owner of the place or admin. value → observation (normal trust flow); planned → no data change."""
        self._require_user(user)
        q = self.repo.get_question(question_id)
        if q is None:
            raise NotFound(f"question not found: {question_id}")
        if q.place_id not in self._managed_place_ids(user):
            raise Forbidden("only the owner of this place or an admin can answer")
        if q.status == "answered":
            raise ConflictError("question already answered")
        text = (text or "").strip()
        if not 1 <= len(text) <= MAX_DESCRIPTION:
            raise ValidationFailed(f"text must have 1..{MAX_DESCRIPTION} characters")
        if value and planned:
            raise ValidationFailed("give value or planned, not both")
        if value and q.feature is None:
            raise ValidationFailed("value needs a question about a feature")
        if value:
            v = _enum(ObservationValue, value, "value")
            self._new_observation(user, q.place_id, q.feature, v, temporary=False, comment=text, photo_ids=[])
            self.recompute(q.place_id, q.feature)
            q.outcome = str(v)
        elif planned:
            q.outcome = "planned"
        q.status, q.answer_text, q.answered_by, q.answered_at = "answered", text, user.id, self.clock.now()
        self._notify(q.author_id, user, "question_answered",
                     f"Odpowiedź na Twoje pytanie — {self._place_name(q.place_id)}: {text}", q.place_id, q.id)
        return q

    def needs_stats(self, user: User | None) -> NeedsStats:
        """Most asked features (what people need to know). Admin: city-wide; owner: own places."""
        self._require_user(user)
        if user.role not in (Role.ADMIN, Role.OWNER):
            raise Forbidden("owner or admin role required")
        places = self._managed_place_ids(user)
        qs = [q for q in self.repo.list_questions() if q.place_id in places]
        counts: dict[FeatureKey, int] = {}
        for q in qs:
            if q.feature:
                counts[q.feature] = counts.get(q.feature, 0) + 1
        by_feature = sorted(counts.items(), key=lambda t: (-t[1], str(t[0])))
        return NeedsStats(by_feature, sum(q.status == "open" for q in qs), sum(q.status == "answered" for q in qs),
                          sum(q.feature is None for q in qs))

    def _managed_place_ids(self, user: User) -> set[str]:
        if user.role == Role.ADMIN:
            return {p.id for p in self.repo.list_places()}
        return {p.id for p in self.repo.list_places() if p.owner_id == user.id}

    # ------------------------------------------------------------------ admin insights (F36)
    def admin_activity(self, admin: User | None, days: int = 30, cell_deg: float = 0.005,
                       bbox: str | None = None) -> list[ActivityCell]:
        """Observations + reports per grid cell in the last `days` (cell centres, busiest first)."""
        self._require_admin(admin)
        if not (1 <= days <= 365 and 0.001 <= cell_deg <= 0.1):
            raise ValidationFailed("days 1..365, cell_deg 0.001..0.1")
        try:
            box = parse_bbox(bbox) if bbox else None
        except ValueError as e:
            raise ValidationFailed(str(e)) from e
        since = self.clock.now() - timedelta(days=days)
        cells: dict[tuple[int, int], ActivityCell] = {}

        def bump(place_id: str, kind: str) -> None:
            place = self.repo.get_place(place_id)
            if place is None or (box and not in_bbox(place.location, box)):
                return
            key = (math.floor(place.location.lat / cell_deg), math.floor(place.location.lon / cell_deg))
            cell = cells.setdefault(key, ActivityCell(round((key[0] + 0.5) * cell_deg, 6),
                                                      round((key[1] + 0.5) * cell_deg, 6), 0, 0))
            setattr(cell, kind, getattr(cell, kind) + 1)

        for p in self.repo.list_places():
            for o in self.repo.list_observations(p.id):
                if o.created_at >= since:
                    bump(p.id, "observations")
        for r in self.repo.list_reports():
            if r.status == "submitted" and r.created_at >= since:
                bump(r.place_id, "reports")
        return sorted(cells.values(), key=lambda c: (-(c.observations + c.reports), c.lat, c.lon))

    def admin_trends(self, admin: User | None, days: int = 30) -> list[TrendDay]:
        """Per-day counts, oldest → newest (today included)."""
        self._require_admin(admin)
        if not 1 <= days <= 365:
            raise ValidationFailed("days 1..365")
        today = self.clock.now().date()
        result = {today - timedelta(days=i): TrendDay(str(today - timedelta(days=i)), 0, 0, 0, 0)
                  for i in range(days - 1, -1, -1)}

        def bump(when: datetime | None, kind: str) -> None:
            if when is not None and when.date() in result:
                day = result[when.date()]
                setattr(day, kind, getattr(day, kind) + 1)

        for p in self.repo.list_places():
            for o in self.repo.list_observations(p.id):
                bump(o.created_at, "observations")
        for r in self.repo.list_reports():
            if r.status == "submitted":
                bump(r.created_at, "reports")
        for q in self.repo.list_questions():
            bump(q.created_at, "questions")
        for item in self.repo.list_queue_items():
            bump(item.created_at, "queue_items")
        return list(result.values())

    def admin_coverage(self, admin: User | None) -> Coverage:
        """Data coverage per category + core features unknown in most places."""
        self._require_admin(admin)
        per: dict[str, CategoryCoverage] = {}
        known_counts: dict[str, int] = {}
        missing = {f: 0 for f in self.CORE_FEATURES}
        for p in self.repo.list_places():
            states = self.repo.states_for(p.id)
            known = [f for f, s in states.items() if s.state != StateValue.UNKNOWN]
            c = per.setdefault(p.category, CategoryCoverage(p.category, 0, 0, 0.0))
            c.places += 1
            c.with_data += bool(known)
            known_counts[p.category] = known_counts.get(p.category, 0) + len(known)
            for f in self.CORE_FEATURES:
                if f not in known:
                    missing[f] += 1
        for c in per.values():
            c.avg_known_features = round(known_counts[c.category] / c.places, 1)
        return Coverage(sorted(per.values(), key=lambda c: (-c.places, c.category)),
                        sorted(missing.items(), key=lambda t: (-t[1], str(t[0]))))

    # ------------------------------------------------------------------ notifications (F35)
    def _notify(self, user_id: str, actor: User | None, kind: str, text: str, place_id: str | None = None,
                ref_id: str | None = None) -> None:
        if actor is not None and actor.id == user_id:
            return  # nobody is notified about their own action
        self.repo.add_notification(Notification(self.ids.new("ntf"), user_id, kind, text[:300], self.clock.now(),
                                                place_id, ref_id))

    def _place_name(self, place_id: str) -> str:
        place = self.repo.get_place(place_id)
        return place.name if place else place_id

    def list_notifications(self, user: User | None, unread_only: bool = False) -> list[Notification]:
        self._require_user(user)
        items = [n for n in self.repo.list_notifications(user.id) if not (unread_only and n.read)]
        return sorted(items, key=lambda n: (n.created_at, _seq(n.id)), reverse=True)

    def mark_notification_read(self, user: User | None, notification_id: str) -> None:
        self._require_user(user)
        n = next((n for n in self.repo.list_notifications(user.id) if n.id == notification_id), None)
        if n is None:
            raise NotFound(f"notification not found: {notification_id}")
        n.read = True

    def mark_all_notifications_read(self, user: User | None) -> int:
        unread = self.list_notifications(user, unread_only=True)
        for n in unread:
            n.read = True
        return len(unread)

    # ------------------------------------------------------------------ needs profile (F31)
    def get_needs_profile(self, user: User | None) -> tuple[list[NeedsProfile], list[FeatureKey]]:
        self._require_user(user)
        return [NeedsProfile(n) for n in user.needs], [FeatureKey(f) for f in user.pref_features]

    def set_needs_profile(self, user: User | None, needs: list[str], features: list[str]
                          ) -> tuple[list[NeedsProfile], list[FeatureKey]]:
        """Needs only (wheelchair, stroller …) — never diagnoses; empty lists clear the profile."""
        self._require_user(user)
        if len(needs or []) > MAX_NEEDS or len(features or []) > MAX_NEEDS:
            raise ValidationFailed(f"at most {MAX_NEEDS} needs and {MAX_NEEDS} features")
        parsed_needs = list(dict.fromkeys(_enum(NeedsProfile, n, "need") for n in needs or []))
        parsed_features = list(dict.fromkeys(_enum(FeatureKey, f, "feature") for f in features or []))
        user.needs, user.pref_features = [str(n) for n in parsed_needs], [str(f) for f in parsed_features]
        return parsed_needs, parsed_features

    # ------------------------------------------------------------------ me (F16)
    def list_favorites(self, user: User | None) -> list[Place]:
        self._require_user(user)
        return [p for p in (self.repo.get_place(i) for i in user.favorite_place_ids) if p]

    def add_favorite(self, user: User | None, place_id: str) -> None:
        self._require_user(user)
        self.get_place(place_id)
        if place_id not in user.favorite_place_ids:
            user.favorite_place_ids.append(place_id)

    def remove_favorite(self, user: User | None, place_id: str) -> None:
        self._require_user(user)
        if place_id in user.favorite_place_ids:
            user.favorite_place_ids.remove(place_id)

    def my_reports(self, user: User | None) -> list[Report]:
        self._require_user(user)
        mine = [(i, r) for i, r in enumerate(self.repo.list_reports()) if r.author_id == user.id]
        return [r for _, r in sorted(mine, key=lambda t: (t[1].created_at, t[0]), reverse=True)]

    # ------------------------------------------------------------------ place screen (F12)
    def verification_for(self, place_id: str) -> Verification:
        states = self.get_accessibility(place_id).values()
        sources = {o.source for o in self.list_observations(place_id)}
        return summarize(states, sources, self.clock.now())

    def place_activity(self, place_id: str, limit: int = 20) -> list[Observation]:
        """Newest first (time, then insertion order). History incl. rejected observations."""
        if not 1 <= limit <= 100:
            raise ValidationFailed("limit: 1..100")
        observations = self.list_observations(place_id, active=False)
        ordered = sorted(enumerate(observations), key=lambda t: (t[1].created_at, t[0]), reverse=True)
        return [o for _, o in ordered][:limit]

    def place_photos(self, place_id: str) -> list[tuple[Photo, Observation]]:
        seen, result = set(), []
        for obs in self.place_activity(place_id, limit=100):
            for photo_id in obs.evidence_ids:
                photo = self.repo.get_photo(photo_id)
                if photo and photo_id not in seen:
                    seen.add(photo_id)
                    result.append((photo, obs))
        return result

    @staticmethod
    def activity_type(obs: Observation) -> str:
        return activity_type(obs, SEED_AUTHOR_ID)

    def yes_features(self, place_id: str) -> list[FeatureKey]:
        return [f for f, s in self.repo.states_for(place_id).items() if s.state == StateValue.YES]

    def resolve_place(self, user: User | None, *, name: str, lat: float, lon: float,
                      category: str = "other", address: str = "") -> tuple[Place, bool]:
        """Map pin + name (nearest stop, reverse geocoding) → place to report on (F12).
        Same rule as the OSM import: the same name within MATCH_RADIUS_M is the same place.
        Returns (place, created)."""
        self._require_user(user)
        name = name.strip()
        if not 1 <= len(name) <= MAX_PLACE_NAME:
            raise ValidationFailed(f"name must have 1..{MAX_PLACE_NAME} characters")
        location = GeoPoint(lat, lon)
        existing = self._find_place(name, location)
        if existing:
            return existing, False
        place = Place(self.ids.new("plc"), name, (category or "").strip() or "other", location,
                      address=address.strip()[:MAX_PLACE_NAME])
        self.repo.add_place(place)
        if user.role != Role.ADMIN:  # F36: places added by users are verified by a moderator
            self.repo.add_queue_item(QueueItem(self.ids.new("q"), place.id, None, self.clock.now(), [],
                                               type="new_place", comments=[{
                                                   "author_id": user.id, "text": f"Nowe miejsce: {name}",
                                                   "created_at": self.clock.now().isoformat()}]))
        return place, True

    # ------------------------------------------------------------------ OSM import (F8)
    async def import_osm(self, admin: User | None, source: str = "osm_file") -> ImportResult:
        """OSM points → open_data observations. Idempotent; matches places by external id or name ≤50 m."""
        self._require_admin(admin)
        osm = {"osm_file": self.osm, "overpass": self.osm_live}.get(source)
        if osm is None:
            raise ValidationFailed(f"unknown or unavailable import source: {source}")
        points = await osm.fetch()

        result = ImportResult(getattr(osm, "last_source", source), points=len(points))
        osm_user = self.repo.get_user(OSM_AUTHOR_ID)
        touched: set[tuple[str, FeatureKey]] = set()
        for p in points:
            if not p.name or p.name == domain_osm.UNNAMED:
                result.skipped_unnamed += 1
                continue
            features = domain_osm.map_features(p)
            if not features:
                result.skipped_no_data += 1
                continue
            place = self._find_place(p.name, GeoPoint(p.lat, p.lon), external_id=p.external_id)
            if place:
                result.places_matched += 1
            else:
                place = Place(self.ids.new("plc_osm"), p.name, domain_osm.map_category(p.category),
                              GeoPoint(p.lat, p.lon), "Import: OpenStreetMap", external_id=p.external_id,
                              place_type=PlaceType.OTHER)
                self.repo.add_place(place)
                result.places_created += 1
            for feature, value in features:
                if self._has_open_data(place.id, feature, value):
                    continue
                self._new_observation(osm_user, place.id, feature, value, temporary=False,
                                      comment="OpenStreetMap", photo_ids=[], source=ObservationSource.OPEN_DATA)
                result.observations += 1
                touched.add((place.id, feature))
        for place_id, feature in touched:
            self.recompute(place_id, feature)
        return result

    async def import_catalog(self, admin: User | None, entries: list[dict]) -> ImportResult:
        """F49: catalogue entries (app/domain/catalog.py) → places (every named one, also without facts), their
        address/contact, and OSM facts as open-data observations. Idempotent: same external id, or the same name
        within 50 m. Indexed lookups: the full city catalogue has ~6,500 places."""
        self._require_admin(admin)
        result = ImportResult("catalog", points=len(entries))
        osm_user = self.repo.get_user(OSM_AUTHOR_ID)
        by_ref: dict[str, Place] = {}
        by_name: dict[str, list[Place]] = {}
        for place in self.repo.list_places():
            if place.external_id:
                by_ref[place.external_id] = place
            by_name.setdefault(place.name.lower(), []).append(place)
        touched: set[tuple[str, FeatureKey]] = set()
        for e in entries:
            name = clean_text(str(e.get("name") or ""))[:MAX_PLACE_NAME]
            if not name:
                result.skipped_unnamed += 1
                continue
            here = GeoPoint(float(e["lat"]), float(e["lon"]))
            place = by_ref.get(e.get("ref")) or next(
                (p for p in by_name.get(name.lower(), []) if haversine_m(p.location, here) <= domain_osm.MATCH_RADIUS_M),
                None)
            contact = {k: str(e[k]) for k in ("phone", "website") if e.get(k)}
            hours = clean_text(str(e.get("opening_hours") or ""))
            if place:
                result.places_matched += 1
                # fill what is missing (catalogue imported before kind/hours existed); values already set stay
                if not place.kind and e.get("kind"):
                    place.kind = clean_text(str(e["kind"]))[:40]
                if not place.opening_hours and hours:
                    place.opening_hours = [{"text": hours}]
                if not place.address and e.get("address"):
                    place.address = clean_text(str(e["address"]))
                place.contact = {**contact, **place.contact}
            else:
                place = Place(self.ids.new("plc_osm"), name, str(e.get("category") or "other"), here,
                              address=clean_text(str(e.get("address") or "")), external_id=e.get("ref"),
                              contact=contact, opening_hours=[{"text": hours}] if hours else [],
                              kind=clean_text(str(e.get("kind") or ""))[:40])
                self.repo.add_place(place)
                if place.external_id:
                    by_ref[place.external_id] = place
                by_name.setdefault(name.lower(), []).append(place)
                result.places_created += 1
            for key, raw in (e.get("features") or {}).items():
                try:
                    feature, value = FeatureKey(key), ObservationValue(raw)
                except ValueError:
                    continue  # not a Rampa feature / value
                if self._has_open_data(place.id, feature, value):
                    continue
                self._new_observation(osm_user, place.id, feature, value, temporary=False,
                                      comment="OpenStreetMap", photo_ids=[], source=ObservationSource.OPEN_DATA)
                result.observations += 1
                touched.add((place.id, feature))
        for place_id, feature in touched:
            self.recompute(place_id, feature)
        return result

    def _find_place(self, name: str, here: GeoPoint, external_id: str | None = None) -> Place | None:
        """Same external id, or the same name (case-insensitive) within MATCH_RADIUS_M."""
        for place in self.repo.list_places():
            if external_id and place.external_id == external_id:
                return place
            if (place.name.lower() == name.lower()
                    and haversine_m(place.location, here) <= domain_osm.MATCH_RADIUS_M):
                return place
        return None

    def _has_open_data(self, place_id: str, feature: FeatureKey, value: ObservationValue) -> bool:
        return any(o.source == ObservationSource.OPEN_DATA and o.value == value
                   and validation.is_active(o)
                   for o in self.repo.list_observations(place_id, feature))

    # ------------------------------------------------------------------ owner (F7)
    def list_owner_places(self, user: User | None) -> list[Place]:
        self._require_owner(user)
        return [p for p in self.repo.list_places() if p.owner_id == user.id]

    def add_owner_observations(self, user: User | None, place_id: str, items: list[dict]) -> list[Observation]:
        """Owner update = new verified_owner observations; never overwrites state or reports."""
        self._require_owner(user)
        place = self.get_place(place_id)
        if place.owner_id != user.id:
            raise Forbidden("you are not the owner of this place")
        if not 1 <= len(items) <= MAX_OWNER_BATCH:
            raise ValidationFailed(f"observations: 1..{MAX_OWNER_BATCH} required")
        parsed = [(_enum(FeatureKey, i.get("feature"), "feature"), _enum(ObservationValue, i.get("value"), "value"),
                   bool(i.get("temporary", False)), str(i.get("comment", "")), self._check_photos(i.get("photo_ids", ())))
                  for i in items]  # validate everything before writing anything
        created = [self._new_observation(user, place_id, f, v, temporary=t, comment=c, photo_ids=ph)
                   for f, v, t, c, ph in parsed]
        for feature in dict.fromkeys(o.feature for o in created):
            self.recompute(place_id, feature)
        return created

    def list_owner_reports(self, user: User | None) -> list[Report]:
        self._require_owner(user)
        owned = {p.id for p in self.list_owner_places(user)}
        reports = [(i, r) for i, r in enumerate(self.repo.list_reports())
                   if r.place_id in owned and r.status != "draft"]
        return [r for _, r in sorted(reports, key=lambda t: (t[1].created_at, t[0]), reverse=True)]

    def assign_owner(self, admin: User | None, place_id: str, user_id: str) -> Place:
        self._require_admin(admin)
        place = self.get_place(place_id)
        owner = self.repo.get_user(user_id)
        if owner is None:
            raise NotFound(f"user not found: {user_id}")
        place.owner_id = owner.id
        if owner.role == Role.USER:
            owner.role = Role.OWNER
        return place

    # ------------------------------------------------------------------ owner extras (F22)
    OWNER_WINDOW = timedelta(days=30)
    CORE_FEATURES = (FeatureKey.STEP_FREE_ENTRANCE, FeatureKey.RAMP, FeatureKey.ELEVATOR, FeatureKey.ACCESSIBLE_TOILET)
    CSV_FIELDS = ["place_id", "feature", "value", "temporary", "comment"]

    def _own_place(self, user: User | None, place_id: str) -> Place:
        self._require_owner(user)
        place = self.get_place(place_id)
        if place.owner_id != user.id:
            raise Forbidden("you are not the owner of this place")
        return place

    def owner_profile(self, user: User | None) -> OwnerProfile:
        self._require_owner(user)
        return OwnerProfile(user.id, user.display_name, user.email, user.role, True,
                            len(self.list_owner_places(user)))

    def update_owner_profile(self, user: User | None, display_name: str | None = None,
                             email: str | None = None) -> OwnerProfile:
        self._require_owner(user)
        if display_name is not None:
            if not 1 <= len(display_name.strip()) <= 100:
                raise ValidationFailed("display_name: 1..100 characters")
            user.display_name = display_name.strip()
        if email is not None:
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
                raise ValidationFailed("invalid e-mail")
            user.email = email.strip()
        return self.owner_profile(user)

    def owner_stats(self, user: User | None) -> OwnerStats:
        places = self.list_owner_places(user)
        ids = {p.id for p in places}
        since = self.clock.now() - self.OWNER_WINDOW
        confidences = [self.verification_for(p.id).confidence for p in places]
        reports = [r for r in self.repo.list_reports()
                   if r.place_id in ids and r.status == "submitted" and r.created_at >= since]
        updates = [o for p in places for o in self.repo.list_observations(p.id)
                   if o.author_id == user.id and o.source == ObservationSource.VERIFIED_OWNER and o.created_at >= since]
        conflicts = [q for q in self.repo.list_queue_items() if q.place_id in ids and q.open_conflict]
        avg = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
        return OwnerStats(len(places), avg, len(reports), len(updates), len(conflicts))

    def update_owner_place(self, user: User | None, place_id: str, *, name: str | None = None,
                           short_description: str | None = None, address: str | None = None,
                           category: str | None = None, contact: dict | None = None) -> Place:
        place = self._own_place(user, place_id)
        if name is not None:
            if not 1 <= len(name.strip()) <= 200:
                raise ValidationFailed("name: 1..200 characters")
            place.name = name.strip()
        for attr, value in (("short_description", short_description), ("address", address),
                            ("category", category)):
            if value is not None:
                setattr(place, attr, value.strip()[:1000])
        if contact is not None:
            unknown = set(contact) - {"phone", "website", "email"}
            checks = {"website": (is_http_url, "website must be an http(s):// URL"),
                      "email": (is_email, "invalid e-mail"), "phone": (is_phone, "invalid phone number")}
            for key, value in contact.items():
                check = checks.get(key)
                if check and str(value).strip() and not check[0](str(value)):
                    raise ValidationFailed(check[1])
            if unknown:
                raise ValidationFailed(f"unknown contact fields: {sorted(unknown)}")
            place.contact = {**place.contact, **{k: str(v).strip() for k, v in contact.items()}}
        return place

    def set_opening_hours(self, user: User | None, place_id: str, hours: list[dict]) -> Place:
        place = self._own_place(user, place_id)
        if len(hours) > 14:
            raise ValidationFailed("max 14 opening-hours entries")
        normalized = []
        for h in hours:
            days = str(h.get("days") or "").strip()
            if not days:
                raise ValidationFailed("opening hours: 'days' is required")
            if h.get("closed"):
                normalized.append({"days": days, "closed": True})
                continue
            start, end = str(h.get("open") or ""), str(h.get("close") or "")
            if not (re.fullmatch(r"\d{2}:\d{2}", start) and re.fullmatch(r"\d{2}:\d{2}", end) and start < end):
                raise ValidationFailed(f"opening hours for {days}: open/close as HH:MM, open < close")
            normalized.append({"days": days, "open": start, "close": end})
        place.opening_hours = normalized
        return place

    def add_place_photo(self, user: User | None, place_id: str, photo_id: str) -> Place:
        place = self._own_place(user, place_id)
        self._check_photos([photo_id])
        if photo_id not in place.photo_ids:
            place.photo_ids.append(photo_id)
        return place

    def remove_place_photo(self, user: User | None, place_id: str, photo_id: str) -> None:
        place = self._own_place(user, place_id)
        if photo_id in place.photo_ids:
            place.photo_ids.remove(photo_id)

    def place_owner_photos(self, place_id: str) -> list[Photo]:
        return [p for p in (self.repo.get_photo(i) for i in self.get_place(place_id).photo_ids) if p]

    def owner_place_stats(self, user: User | None, place_id: str) -> OwnerPlaceStats:
        self._own_place(user, place_id)
        observations = self.repo.list_observations(place_id)
        by_source: dict[str, int] = {}
        for o in observations:
            by_source[str(o.source)] = by_source.get(str(o.source), 0) + 1
        conflicts = sum(1 for q in self.repo.list_queue_items()
                        if q.place_id == place_id and q.open_conflict)
        v = self.verification_for(place_id)
        return OwnerPlaceStats(len(observations), by_source, sum(o.up_votes for o in observations),
                               sum(o.down_votes for o in observations), conflicts, v.last_verified, v.confidence)

    def _owned_report(self, user: User | None, report_id: str) -> Report:
        self._require_owner(user)
        report = self.repo.get_report(report_id)
        if report is None:
            raise NotFound(f"report not found: {report_id}")
        self._own_place(user, report.place_id)
        if report.status != "submitted":
            raise ConflictError("only submitted reports can be answered")
        return report

    def reply_to_report(self, user: User | None, report_id: str, text: str) -> Report:
        report = self._owned_report(user, report_id)
        text = (text or "").strip()
        if not 1 <= len(text) <= MAX_DESCRIPTION:
            raise ValidationFailed(f"reply must have 1..{MAX_DESCRIPTION} characters")
        report.replies.append({"author_id": user.id, "text": text, "created_at": self.clock.now().isoformat()})
        self._notify(report.author_id, user, "report_reply",
                     f"Właściciel odpowiedział na Twoje zgłoszenie — {self._place_name(report.place_id)}: {text}",
                     report.place_id, report.id)
        return report

    def approve_report(self, user: User | None, report_id: str) -> Observation:
        """Owner confirms a user's report → verified_owner observation with the same value."""
        report = self._owned_report(user, report_id)
        if report.owner_status == "approved":
            raise ConflictError("report already approved")
        value = REPORT_VALUE[report.current_state]
        obs = self._new_observation(user, report.place_id, report.element, value,
                                    temporary=report.nature == Nature.TEMPORARY,
                                    comment=f"Potwierdzone przez właściciela: {report.description}", photo_ids=[])
        report.owner_status = "approved"
        self.recompute(report.place_id, report.element)
        self._notify(report.author_id, user, "report_approved",
                     f"Właściciel potwierdził Twoje zgłoszenie — {self._place_name(report.place_id)}",
                     report.place_id, report.id)
        return obs

    def owner_reminders(self, user: User | None) -> list[Reminder]:
        reminders = []
        for place in self.list_owner_places(user):
            states = self.get_accessibility(place.id)
            for f in self.CORE_FEATURES:
                if states[f].state == StateValue.UNKNOWN:
                    reminders.append(Reminder(place.id, "missing_data",
                                              f"Uzupełnij dane: {LABELS_PL[f]} — {place.name}", "normal", f))
            if self.verification_for(place.id).status == "needs_update":
                reminders.append(Reminder(place.id, "stale_data",
                                          f"Sprawdź aktualność danych — {place.name}", "normal"))
            for q in self.repo.list_queue_items():
                if q.place_id == place.id and q.open_conflict:
                    reminders.append(Reminder(place.id, "conflict",
                                              f"Wyjaśnij sprzeczne zgłoszenia: {LABELS_PL[q.feature]} — {place.name}",
                                              "high", q.feature))
            for q in self.repo.list_questions():
                if q.place_id == place.id and q.status == "open":
                    reminders.append(Reminder(place.id, "unanswered_question",
                                              f"Odpowiedz na pytanie: {q.text} — {place.name}", "high", q.feature))
            for r in self.repo.list_reports():
                if r.place_id == place.id and r.status == "submitted" and not r.replies and not r.owner_status:
                    reminders.append(Reminder(place.id, "unanswered_report",
                                              f"Odpowiedz na zgłoszenie: {r.description} — {place.name}", "high",
                                              r.element))
        return sorted(reminders, key=lambda r: r.priority != "high")

    def owner_suggestions(self, user: User | None) -> list[OwnerSuggestion]:
        result = []
        for place in self.list_owner_places(user):
            for f, st in self.get_accessibility(place.id).items():
                if st.state == StateValue.NO:
                    result.append(OwnerSuggestion(place.id, f, f"Rozważ: {LABELS_PL[f]} — {place.name}"))
        return result

    def owner_batch(self, user: User | None, items: list[dict]) -> list[Observation]:
        """Several own places at once; validated completely before anything is written."""
        self._require_owner(user)
        if not 1 <= len(items) <= 50:
            raise ValidationFailed("batch: 1..50 items")
        parsed = []
        for i in items:
            self._own_place(user, str(i.get("place_id")))
            parsed.append((i["place_id"], _enum(FeatureKey, i.get("feature"), "feature"),
                           _enum(ObservationValue, i.get("value"), "value"), bool(i.get("temporary", False)),
                           str(i.get("comment") or ""), self._check_photos(i.get("photo_ids") or ())))  # noqa: E501
        created = [self._new_observation(user, pid, f, v, temporary=t, comment=c, photo_ids=ph)
                   for pid, f, v, t, c, ph in parsed]
        for pid, f in dict.fromkeys((o.place_id, o.feature) for o in created):
            self.recompute(pid, f)
        return created

    def owner_csv_template(self) -> str:
        return ",".join(self.CSV_FIELDS) + "\nplc_mnk,ramp,yes,false,Podjazd od strony al. 3 Maja\n"

    def owner_csv_import(self, user: User | None, text: str) -> CsvImportResult:
        """Valid rows are imported (verified_owner); invalid rows reported with their file line number."""
        self._require_owner(user)
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None or [f.strip() for f in reader.fieldnames] != self.CSV_FIELDS:
            raise ValidationFailed(f"CSV header must be: {','.join(self.CSV_FIELDS)}")
        rows = list(reader)
        if len(rows) > 500:
            raise ValidationFailed("max 500 rows")
        imported, errors, touched = 0, [], set()
        for line, row in enumerate(rows, start=2):
            try:
                place_id = (row.get("place_id") or "").strip()
                self._own_place(user, place_id)
                feature = _enum(FeatureKey, (row.get("feature") or "").strip(), "feature")
                value = _enum(ObservationValue, (row.get("value") or "").strip(), "value")
                temporary = (row.get("temporary") or "").strip().lower() in ("true", "1", "yes", "tak")
                self._new_observation(user, place_id, feature, value, temporary=temporary,
                                      comment=(row.get("comment") or "").strip(), photo_ids=[])
                touched.add((place_id, feature))
                imported += 1
            except (ValidationFailed, Forbidden, NotFound) as e:
                errors.append({"row": line, "message": e.message})
        for place_id, feature in touched:
            self.recompute(place_id, feature)
        return CsvImportResult(imported, errors)

    @staticmethod
    def _require_owner(user: User | None) -> None:
        if user is None:
            raise Unauthorized("login required")
        if user.role != Role.OWNER:
            raise Forbidden("owner role required")

    # ------------------------------------------------------------------ AI suggestions (F6)
    async def analyze_image(self, user: User | None, photo_ids: list[str],
                            place_id: str | None = None, on_step=None,
                            expected: dict | None = None) -> ImageTagsResult:
        """Suggestions for the report form. Never changes feature state.
        on_step(event): progress of a vision chain (F44 stream); ignored by a single model.
        expected {element, current_state?} (else the photos' upload metadata, F45): the model's suggestion
        must agree, otherwise the photos are deleted and PhotoMismatch is raised."""
        self._require_user(user)
        if not 1 <= len(photo_ids) <= MAX_PHOTOS:
            raise ValidationFailed(f"photo_ids: 1..{MAX_PHOTOS} required")
        photos = [self.repo.get_photo(p) for p in self._check_photos(photo_ids)]
        expected = self._expected(expected, photos)
        if place_id:
            self.get_place(place_id)
        if self.vision is None:
            raise ValidationFailed("AI is not configured")

        if on_step and getattr(self.vision, "REPORTS_STEPS", False):
            analyses = [await self.vision.analyze(p.path, p.original_name, on_step=on_step) for p in photos]
        else:
            analyses = [await self.vision.analyze(p.path, p.original_name) for p in photos]
        real = [a for a in analyses if a.real_place]
        if not real:
            raise NotARealPlace("no photo shows a real place (screenshot or graphic?)")

        best = max(real, key=lambda a: a.confidence)
        suggested = suggestions.suggest(best).suggested
        # A verdict needs a real look at the photo: the mock answering as a fallback (the real model failed) is a
        # fixed sample, not about this photo. Only AI_MODE=mock itself (the demo: vision is the mock) still checks.
        looked = best.model != "mock" or getattr(self.vision, "LABEL", None) == "mock"
        if expected and suggested and looked and (
                suggested.element.value != expected["element"]
                or (expected["current_state"] and suggested.current_state.value != expected["current_state"])):
            deleted = await self._delete_unused_photos(photos)
            raise PhotoMismatch(
                f"photo shows {suggested.element.value}/{suggested.current_state.value}, "
                f"not {expected['element']}/{expected['current_state'] or 'any'}",
                {"expected": expected,
                 "suggested": {"element": suggested.element.value, "current_state": suggested.current_state.value,
                               "severity": suggested.severity.value},
                 "description": best.description, "deleted_photo_ids": deleted})
        tags: dict[str, suggestions.Tag] = {}
        for a in real:
            for tag in suggestions.suggest(a).tags:
                if tag.label not in tags or tag.confidence > tags[tag.label].confidence:
                    tags[tag.label] = tag
        return ImageTagsResult(
            analysis=best,
            tags=list(tags.values()),
            detected="; ".join(a.description for a in real if a.description),
            suggested=suggestions.suggest(best).suggested,
            model=best.model,
        )

    # ------------------------------------------------------------------ admin panel (F13)
    def admin_stats(self, admin: User | None) -> AdminStats:
        self._require_admin(admin)
        places = self.repo.list_places()
        observations = [o for p in places for o in self.repo.list_observations(p.id)]
        states = [s for p in places for s in self.repo.states_for(p.id).values()]
        submitted = [r for r in self.repo.list_reports() if r.status != "draft"]
        return compute_stats(reports=submitted, observations=observations,
                             queue=self.repo.list_queue_items(), states=states, places=len(places),
                             now=self.clock.now())

    def place_history(self, user: User | None, place_id: str) -> list[HistoryEvent]:
        """Audit trail — admin, or the owner of this place."""
        self._require_user(user)
        place = self.get_place(place_id)
        if not (user.role == Role.ADMIN or (user.role == Role.OWNER and place.owner_id == user.id)):
            raise Forbidden("history is visible to admins and the place owner")
        queue = [q for q in self.repo.list_queue_items() if q.place_id == place_id]
        return build_history(self.repo.list_observations(place_id), queue)

    def parse_text(self, user: User | None, text: str) -> list[TextSuggestion]:
        """F19: description → suggested observations (rules). Suggestion only."""
        self._require_user(user)
        if not 1 <= len((text or "").strip()) <= MAX_DESCRIPTION:
            raise ValidationFailed(f"text must have 1..{MAX_DESCRIPTION} characters")
        return parse_text(text)

    # ------------------------------------------------------------------ admin extras (F21)
    def place_confidence(self, admin: User | None, place_id: str) -> "PlaceConfidence":
        self._require_admin(admin)
        states = [st for st in self.get_accessibility(place_id).values() if st.state != StateValue.UNKNOWN]
        groups: dict[str, list[float]] = {}
        for st in states:
            groups.setdefault(str(FEATURE_GROUP[st.feature]), []).append(st.confidence)
        by_group = {g: round(sum(v) / len(v), 2) for g, v in groups.items()}
        overall = round(sum(st.confidence for st in states) / len(states), 2) if states else 0.0
        conflict = any(st.validation == ValidationStatus.CONFLICT for st in states)
        note = "Dane są częściowo sprzeczne i wymagają weryfikacji." if conflict else ""
        return PlaceConfidence(overall, by_group, note)

    def add_queue_comment(self, admin: User | None, item_id: str, text: str) -> QueueItem:
        item = self.get_queue_item(admin, item_id)
        text = (text or "").strip()
        if not 1 <= len(text) <= MAX_DESCRIPTION:
            raise ValidationFailed(f"comment must have 1..{MAX_DESCRIPTION} characters")
        item.comments.append({"author_id": admin.id, "text": text, "created_at": self.clock.now().isoformat()})
        return item

    def flag_observation(self, admin: User | None, observation_id: str, reason: str) -> Observation:
        """Abuse / spam: excluded from trust and conflicts; history kept."""
        self._require_admin(admin)
        obs = self._get_observation(observation_id)
        reason = (reason or "").strip()
        if not 1 <= len(reason) <= 200:
            raise ValidationFailed("reason must have 1..200 characters")
        obs.validation, obs.flag_reason = ValidationStatus.FLAGGED, reason
        self.recompute(obs.place_id, obs.feature)
        return obs

    def merge_places(self, admin: User | None, source_id: str, target_id: str) -> Place:
        """Duplicate → target: move observations, reports, queue items, favourites, requests; delete duplicate."""
        self._require_admin(admin)
        if source_id == target_id:
            raise ValidationFailed("cannot merge a place into itself")
        self.get_place(source_id)
        target = self.get_place(target_id)
        features = set()
        for o in self.repo.list_observations(source_id):
            o.place_id = target_id
            features.add(o.feature)
        for r in self.repo.list_reports():
            if r.place_id == source_id:
                r.place_id = target_id
        for q in self.repo.list_queue_items():
            if q.place_id == source_id:
                q.place_id = target_id
                if q.type == "new_place" and q.pending:  # F36: the duplicate was merged
                    q.status, q.decision, q.resolved_at = QueueStatus.RESOLVED, "merged", self.clock.now()
        for req in self.repo.list_ownership_requests():
            if req.place_id == source_id:
                req.place_id = target_id
        for q in self.repo.list_questions():
            if q.place_id == source_id:
                q.place_id = target_id
        for u in [self.repo.get_user(i) for i in self.all_user_ids()]:
            if u and source_id in u.favorite_place_ids:
                u.favorite_place_ids = list(dict.fromkeys(
                    target_id if f == source_id else f for f in u.favorite_place_ids))
        self.repo.delete_place(source_id)
        for feature in features:
            self.recompute(target_id, feature)
        return target

    def all_user_ids(self) -> list[str]:
        return [i for i in self.repo.all_ids() if i.startswith("usr_")]

    def revalidate(self, admin: User | None) -> dict:
        """Recompute validation + trust for every place feature."""
        self._require_admin(admin)
        places = self.repo.list_places()
        count = 0
        for p in places:
            features = set(self.repo.states_for(p.id)) | {o.feature for o in self.repo.list_observations(p.id)}
            for feature in features:
                self.recompute(p.id, feature)
                count += 1
        return {"places": len(places), "features": count}

    def request_ownership(self, user: User | None, place_id: str, justification: str) -> OwnershipRequest:
        """"Jestem właścicielem" — any logged-in user applies; an admin verifies."""
        self._require_user(user)
        self.get_place(place_id)
        req = OwnershipRequest(self.ids.new("own"), place_id, user.id, (justification or "").strip()[:1000],
                               self.clock.now())
        self.repo.add_ownership_request(req)
        return req

    def list_ownership_requests(self, admin: User | None, status: str = "pending") -> list[OwnershipRequest]:
        self._require_admin(admin)
        if status not in ("pending", "approved", "rejected", "all"):
            raise ValidationFailed("status: pending|approved|rejected|all")
        return [r for r in self.repo.list_ownership_requests() if status == "all" or r.status == status]

    def verify_ownership(self, admin: User | None, request_id: str, approved: bool) -> OwnershipRequest:
        self._require_admin(admin)
        req = self.repo.get_ownership_request(request_id)
        if req is None:
            raise NotFound(f"ownership request not found: {request_id}")
        if req.status != "pending":
            raise ConflictError(f"request already {req.status}")
        if approved:
            self.assign_owner(admin, req.place_id, req.user_id)
        req.status, req.decided_at = ("approved" if approved else "rejected"), self.clock.now()
        self._notify(req.user_id, admin, "ownership_decided",
                     f"Wniosek o przejęcie {'zaakceptowany' if approved else 'odrzucony'} — "
                     f"{self._place_name(req.place_id)}", req.place_id, req.id)
        return req

    # ------------------------------------------------------------------ moderation (F4)
    def list_queue(self, admin: User | None, filter: str = "all", status: str = "open") -> list[QueueItem]:
        self._require_admin(admin)
        items = self.repo.list_queue_items()
        if filter not in ("all", "conflict", "abuse", "new_place") or status not in ("open", "escalated",
                                                                                    "resolved", "all"):
            raise ValidationFailed("filter must be all|conflict|abuse|new_place, status open|escalated|resolved|all")
        if filter != "all":
            items = [q for q in items if q.type == filter]
        if status != "all":
            items = [q for q in items if q.status == status]
        return items

    def get_queue_item(self, admin: User | None, item_id: str) -> QueueItem:
        self._require_admin(admin)
        item = self.repo.get_queue_item(item_id)
        if item is None:
            raise NotFound(f"queue item not found: {item_id}")
        return item

    def decide(self, admin: User | None, item_id: str, action: str,
               winning_observation_id: str | None = None, comment: str = "") -> FeatureStateRecord | None:
        """confirm: winner kept + admin observation, opposite values REJECTED; reject: all REJECTED;
        escalate: handed to a coordinator, data unchanged, decidable later.
        Abuse items: confirm → observation FLAGGED; reject → report dismissed.
        Observations are never deleted — only their validation changes."""
        item = self.get_queue_item(admin, item_id)
        action_v = _enum(DecisionAction, action, "action")
        if not item.pending:
            raise ConflictError(f"queue item already resolved: {item_id}")
        if action_v == DecisionAction.ESCALATE:
            if item.status == QueueStatus.ESCALATED:
                raise ConflictError(f"queue item already escalated: {item_id}")
            item.status, item.decision = QueueStatus.ESCALATED, "escalated"
            if comment.strip():
                self.add_queue_comment(admin, item_id, comment)
            return self.recompute(item.place_id, item.feature) if item.feature else None
        if item.type == "abuse":
            return self._decide_abuse(item, action_v)
        if item.type == "new_place":
            return self._decide_new_place(item, action_v)
        observations = [self._get_observation(i) for i in item.observation_ids]

        if action_v == DecisionAction.CONFIRM:
            if winning_observation_id not in item.observation_ids:
                raise ValidationFailed("confirm requires winning_observation_id from this queue item")
            winner = self._get_observation(winning_observation_id)
            for o in observations:
                o.validation = ValidationStatus.VALID if o.value == winner.value else ValidationStatus.REJECTED
            item.status, item.decision, item.resolved_at = QueueStatus.RESOLVED, "approved", self.clock.now()
            self._new_observation(admin, item.place_id, item.feature, winner.value, temporary=winner.temporary,
                                  comment=comment or "Potwierdzone przez moderatora", photo_ids=[])
        else:
            for o in observations:
                o.validation = ValidationStatus.REJECTED
            item.status, item.decision, item.resolved_at = QueueStatus.RESOLVED, "rejected", self.clock.now()
        label, place = LABELS_PL[item.feature], self._place_name(item.place_id)
        for author in dict.fromkeys(o.author_id for o in observations):
            ok = any(o.validation == ValidationStatus.VALID for o in observations if o.author_id == author)
            self._notify(author, admin, "observation_confirmed" if ok else "observation_rejected",
                         f"Moderator {'potwierdził' if ok else 'odrzucił'} Twoją informację: {label} — {place}",
                         item.place_id, item.id)
        return self.recompute(item.place_id, item.feature)

    def _decide_new_place(self, item: QueueItem, action: DecisionAction) -> None:
        """confirm → place accepted; reject → deleted only if nobody added data (observations are never deleted)."""
        if action == DecisionAction.REJECT:
            if self.repo.list_observations(item.place_id):
                raise ConflictError("place already has observations — merge it into the right place instead")
            self.repo.delete_place(item.place_id)
        item.status, item.resolved_at = QueueStatus.RESOLVED, self.clock.now()
        item.decision = "approved" if action == DecisionAction.CONFIRM else "rejected"
        return None

    def _decide_abuse(self, item: QueueItem, action: DecisionAction) -> FeatureStateRecord:
        obs = self._get_observation(item.observation_ids[0])
        if action == DecisionAction.CONFIRM:
            reasons = "; ".join(c["text"] for c in item.comments)
            obs.validation, obs.flag_reason = ValidationStatus.FLAGGED, f"Zgłoszenia nadużycia: {reasons}"[:200]
        item.status, item.resolved_at = QueueStatus.RESOLVED, self.clock.now()
        item.decision = "approved" if action == DecisionAction.CONFIRM else "rejected"
        verdict = "oznaczona jako nadużycie" if action == DecisionAction.CONFIRM else "pozostaje bez zmian"
        for reporter in dict.fromkeys(c["author_id"] for c in item.comments):
            self._notify(reporter, None, "abuse_decided",
                         f"Dziękujemy za zgłoszenie — informacja {verdict} ({self._place_name(item.place_id)})",
                         item.place_id, item.id)
        return self.recompute(item.place_id, item.feature)

    def report_abuse(self, user: User | None, observation_id: str, reason: str) -> QueueItem:
        """F26: any user reports spam / false data → moderation queue (type abuse). Once per user."""
        self._require_user(user)
        obs = self._get_observation(observation_id)
        reason = (reason or "").strip()
        if not 1 <= len(reason) <= 200:
            raise ValidationFailed("reason must have 1..200 characters")
        if obs.author_id == user.id:
            raise ValidationFailed("cannot report your own observation")
        items = [q for q in self.repo.list_queue_items() if q.type == "abuse" and observation_id in q.observation_ids]
        if any(c["author_id"] == user.id for q in items for c in q.comments):
            raise ConflictError("you already reported this observation")
        item = next((q for q in items if q.pending), None)
        if item is None:
            item = QueueItem(self.ids.new("q"), obs.place_id, obs.feature, self.clock.now(), [obs.id], type="abuse")
            self.repo.add_queue_item(item)
        item.comments.append({"author_id": user.id, "text": reason, "created_at": self.clock.now().isoformat()})
        return item

    # ------------------------------------------------------------------ observations (F3)
    def recompute(self, place_id: str, feature: FeatureKey) -> FeatureStateRecord:
        """observations → validation (conflict → queue) → trust → state. Sync block = atomic."""
        observations = self.repo.list_observations(place_id, feature)
        now = self.clock.now()
        for o in observations:
            o.confidence = trust.observation_confidence(o, now)
        conflicting = validation.conflicting_observations(observations, self.clock.now())
        item = self.repo.find_open_queue_item(place_id, feature)
        if conflicting:
            for o in conflicting:
                o.validation = ValidationStatus.CONFLICT
            new_ids = [o.id for o in conflicting]
            if item:
                item.observation_ids = list(dict.fromkeys(item.observation_ids + new_ids))
            else:
                item = QueueItem(self.ids.new("q"), place_id, feature, self.clock.now(), new_ids)
                self.repo.add_queue_item(item)
        state = trust.compute_feature_state(place_id, feature, observations, conflict_open=item is not None,
                                            now=now)
        self.repo.save_state(state)
        return state

    async def upload_photo(self, user: User | None, chunks: AsyncIterator[bytes], filename: str,
                           place_id: str | None = None, element: str | None = None,
                           current_state: str | None = None) -> Photo:
        """Store a photo; optional metadata (F45) = what the user says it shows, checked by analyze_image."""
        self._require_user(user)
        if place_id and self.repo.get_place(place_id) is None:
            raise ValidationFailed(f"unknown place_id: {place_id}")
        element = _enum(FeatureKey, element, "element").value if element else None
        current_state = _enum(CurrentState, current_state, "current_state").value if current_state else None
        data = bytearray()
        async for chunk in chunks:
            data.extend(chunk)
            if len(data) > MAX_PHOTO_BYTES:
                raise FileTooLarge(f"photo larger than {MAX_PHOTO_BYTES} bytes")
        ext = next((e for sig, e in IMAGE_SIGNATURES.items() if data.startswith(sig)), None)
        if ext is None:
            raise ValidationFailed("only PNG or JPG images are accepted")
        photo_id = self.ids.new("ph")

        async def one_chunk():
            yield bytes(data)

        path, url = await self.storage.save(one_chunk(), f"{photo_id}.{ext}")
        photo = Photo(photo_id, path, url, original_name=clean_text(filename)[:MAX_PLACE_NAME] or "upload",
                      place_id=place_id or None, element=element, current_state=current_state)
        self.repo.add_photo(photo)
        return photo

    REPORT_FIELDS = ("element", "current_state", "severity", "nature", "description")

    def _parse_report_fields(self, *, complete: bool, **raw) -> dict:
        """Validate given fields; with complete=True all REPORT_FIELDS must be present (submit)."""
        out = {}
        for name, enum_cls in (("element", FeatureKey), ("current_state", CurrentState),
                               ("severity", Severity), ("nature", Nature)):
            if raw.get(name) is not None:
                out[name] = _enum(enum_cls, raw[name], name)
        if raw.get("description") is not None:
            text = raw["description"].strip()
            if len(text) > MAX_DESCRIPTION or (complete and not text):
                raise ValidationFailed(f"description must have 1..{MAX_DESCRIPTION} characters")
            out["description"] = text
        if raw.get("photo_ids") is not None:
            out["photo_ids"] = self._check_photos(raw["photo_ids"])
        return out

    def create_report(self, user: User | None, *, place_id: str, element: str | None = None,
                      current_state: str | None = None, severity: str | None = None, nature: str | None = None,
                      description: str | None = None, photo_ids: list[str] | tuple = (),
                      draft: bool = False) -> Report:
        """draft=True: only place required, no observation. Else submitted immediately (F3 behaviour)."""
        self._require_user(user)
        self.get_place(place_id)
        fields = self._parse_report_fields(complete=not draft, element=element, current_state=current_state,
                                           severity=severity, nature=nature, description=description,
                                           photo_ids=photo_ids)
        report = Report(self.ids.new("rep"), place_id, user.id, fields.get("element"), fields.get("current_state"),
                        fields.get("severity"), fields.get("nature"), fields.get("description"), self.clock.now(),
                        photo_ids=fields.get("photo_ids", []), status="draft")
        if not draft:
            self._require_complete(report)
            self._submit(user, report)
        self.repo.add_report(report)
        return report

    def update_report(self, user: User | None, report_id: str, **raw) -> Report:
        report = self._own_draft(user, report_id)
        for name, value in self._parse_report_fields(complete=False, **raw).items():
            setattr(report, name, value)
        return report

    def submit_report(self, user: User | None, report_id: str) -> Report:
        report = self._own_draft(user, report_id)
        self._require_complete(report)
        self._submit(user, report)
        return report

    def _own_draft(self, user: User | None, report_id: str) -> Report:
        self._require_user(user)
        report = self.repo.get_report(report_id)
        if report is None:
            raise NotFound(f"report not found: {report_id}")
        if report.author_id != user.id:
            raise Forbidden("only the author can edit or submit a report")
        if report.status != "draft":
            raise ConflictError(f"report already {report.status}")
        return report

    def _require_complete(self, report: Report) -> None:
        missing = [f for f in self.REPORT_FIELDS if not getattr(report, f)]
        if missing:
            raise ValidationFailed(f"missing fields: {', '.join(missing)}")

    def _submit(self, user: User, report: Report) -> None:
        value = REPORT_VALUE[report.current_state]
        obs = self._new_observation(user, report.place_id, report.element, value,
                                    temporary=report.nature == Nature.TEMPORARY, comment=report.description,
                                    photo_ids=report.photo_ids, report_id=report.id)
        report.observation_ids = [obs.id]
        report.status = "submitted"
        self.recompute(report.place_id, report.element)

    def get_report(self, user: User | None, report_id: str) -> Report:
        self._require_user(user)
        report = self.repo.get_report(report_id)
        if report is None:
            raise NotFound(f"report not found: {report_id}")
        if report.author_id != user.id and user.role != Role.ADMIN:
            raise Forbidden("only the author or an admin can see this report")
        return report

    def add_observation(self, user: User | None, place_id: str, *, feature: str, value: str,
                        temporary: bool = False, comment: str = "",
                        photo_ids: list[str] | tuple = (), valid_until: str | datetime | None = None) -> Observation:
        self._require_user(user)
        self.get_place(place_id)
        feature_v = _enum(FeatureKey, feature, "feature")
        value_v = _enum(ObservationValue, value, "value")
        until = self._parse_valid_until(valid_until)
        obs = self._new_observation(user, place_id, feature_v, value_v, temporary=temporary or until is not None,
                                    comment=comment, photo_ids=self._check_photos(photo_ids))
        obs.valid_until = until
        self.recompute(place_id, feature_v)
        return obs

    def _parse_valid_until(self, raw: str | datetime | None) -> datetime | None:
        if raw in (None, ""):
            return None
        try:
            until = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        except ValueError as e:
            raise ValidationFailed("valid_until must be an ISO date-time") from e
        if until.tzinfo is None:
            until = until.replace(tzinfo=self.clock.now().tzinfo)
        if until <= self.clock.now():
            raise ValidationFailed("valid_until must be in the future")
        return until

    def _refresh_expired(self, place_id: str) -> None:
        """Temporary issues past valid_until stop counting: recompute their features lazily on read."""
        now = self.clock.now()
        for feature, state in self.repo.states_for(place_id).items():
            obs = self.repo.get_observation(state.active_observation_id) if state.active_observation_id else None
            if obs and obs.valid_until and obs.valid_until <= now:
                self.recompute(place_id, feature)

    def map_observations(self, *, bbox: str | None = None, active: bool = True, feature: str | None = None,
                         value: str | None = None, current: bool = False, since: str | None = None,
                         limit: int = 200) -> list[tuple[Observation, Place, str | None]]:
        """F24: observations across places for the map, newest first, with place + report severity."""
        if not 1 <= limit <= 500:
            raise ValidationFailed("limit: 1..500")
        try:
            box = parse_bbox(bbox) if bbox else None
        except ValueError as e:
            raise ValidationFailed(str(e)) from e
        feature_v = _enum(FeatureKey, feature, "feature") if feature else None
        value_v = _enum(ObservationValue, value, "value") if value else None
        since_dt = None
        if since:
            try:  # "+01:00" often arrives as " 01:00" when not URL-encoded
                since_dt = datetime.fromisoformat(re.sub(r" (\d{2}:\d{2})$", r"+\1", since.strip()))
            except ValueError as e:
                raise ValidationFailed("since must be an ISO date-time") from e
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=self.clock.now().tzinfo)
        now = self.clock.now()

        rows = []
        for place in self.repo.list_places():
            if box and not in_bbox(place.location, box):
                continue
            if current:
                self._refresh_expired(place.id)
            states = self.repo.states_for(place.id) if current else {}
            for o in self.repo.list_observations(place.id, feature_v):
                if active and (not validation.is_active(o) or trust.is_expired(o, now)):
                    continue
                if value_v and o.value != value_v:
                    continue
                if since_dt and o.created_at < since_dt:
                    continue
                if current and (o.feature not in states or states[o.feature].active_observation_id != o.id):
                    continue
                report = self.repo.get_report(o.report_id) if o.report_id else None
                severity = str(report.severity) if report and report.severity else None
                rows.append((o, place, severity))
        seq = lambda o: int(o.id.rsplit("_", 1)[-1]) if o.id.rsplit("_", 1)[-1].isdigit() else 0  # noqa: E731
        rows.sort(key=lambda r: (r[0].created_at, seq(r[0])), reverse=True)
        return rows[:limit]

    def list_observations(self, place_id: str, feature: FeatureKey | None = None,
                          active: bool = True) -> list[Observation]:
        self.get_place(place_id)
        observations = self.repo.list_observations(place_id, feature)
        if active:
            observations = [o for o in observations if validation.is_active(o)]
        return observations

    def vote(self, user: User | None, observation_id: str, value: int) -> tuple[Observation, FeatureStateRecord]:
        self._require_user(user)
        if value not in (1, -1):
            raise ValidationFailed("vote value must be 1 or -1")
        obs = self._get_observation(observation_id)
        if obs.author_id == user.id:
            raise ValidationFailed("you cannot vote on your own observation")
        obs.votes[user.id] = value
        return obs, self.recompute(obs.place_id, obs.feature)

    def remove_vote(self, user: User | None, observation_id: str) -> None:
        self._require_user(user)
        obs = self._get_observation(observation_id)
        obs.votes.pop(user.id, None)
        self.recompute(obs.place_id, obs.feature)

    def _new_observation(self, user: User, place_id: str, feature: FeatureKey, value: ObservationValue, *,
                         temporary: bool, comment: str, photo_ids: list[str],
                         report_id: str | None = None, source: ObservationSource | None = None) -> Observation:
        source = source or self._source_for(user, place_id)
        obs = Observation(self.ids.new("obs"), place_id, feature, value, source, user.id, self.clock.now(),
                          temporary=temporary, comment=clean_text(comment or ""), evidence_ids=list(photo_ids),
                          report_id=report_id)
        self.repo.add_observation(obs)
        return obs

    def _source_for(self, user: User, place_id: str) -> ObservationSource:
        """admin → admin; owner of this place → verified_owner; else community."""
        place = self.repo.get_place(place_id)
        if user.role == Role.ADMIN:
            return ObservationSource.ADMIN
        if place is not None and place.owner_id == user.id:
            return ObservationSource.VERIFIED_OWNER
        return ObservationSource.COMMUNITY

    def _get_observation(self, observation_id: str) -> Observation:
        obs = self.repo.get_observation(observation_id)
        if obs is None:
            raise NotFound(f"observation not found: {observation_id}")
        return obs

    @staticmethod
    def _expected(expected: dict | None, photos: list[Photo]) -> dict | None:
        """F45: {element, current_state} to confirm — from the request, else the first photo with metadata."""
        if expected is None:
            meta = next((p for p in photos if p.element), None)
            if meta is None:
                return None
            expected = {"element": meta.element, "current_state": meta.current_state}
        state = expected.get("current_state")
        return {"element": _enum(FeatureKey, expected.get("element"), "expected.element").value,
                "current_state": _enum(CurrentState, state, "expected.current_state").value if state else None}

    async def _delete_unused_photos(self, photos: list[Photo]) -> list[str]:
        """Delete photos that are not evidence yet (record + file); returns the deleted ids."""
        used = {i for r in self.repo.list_reports() for i in r.photo_ids}
        used |= {i for p in self.repo.list_places() for i in p.photo_ids}
        used |= {i for p in self.repo.list_places() for o in self.repo.list_observations(p.id) for i in o.evidence_ids}
        deleted = []
        for photo in photos:
            if photo.id in used:
                continue
            self.repo.delete_photo(photo.id)
            try:
                await self.storage.delete(photo.path)
            except Exception:  # noqa: BLE001 — the record is gone; a stray file is harmless
                log.warning("could not delete photo file %s", photo.path)
            deleted.append(photo.id)
        return deleted

    def _check_photos(self, photo_ids) -> list[str]:
        photo_ids = list(photo_ids)
        if len(photo_ids) > MAX_PHOTOS:
            raise ValidationFailed(f"max {MAX_PHOTOS} photos")
        missing = [p for p in photo_ids if self.repo.get_photo(p) is None]
        if missing:
            raise ValidationFailed(f"unknown photo ids: {missing}")
        return photo_ids

    @staticmethod
    def _require_user(user: User | None) -> None:
        if user is None:
            raise Unauthorized("login required")
