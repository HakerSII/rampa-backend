"""All MVP use cases (application layer). Depends only on domain + ports."""
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

from app.application.ports import (
    Clock,
    FileStorage,
    IdentityVerifier,
    IdGenerator,
    OsmSource,
    Repo,
    VisionAnalyzer,
)
from app.domain import check as domain_check, osm as domain_osm, suggestions, trust, validation
from app.domain.geo import haversine_m, in_bbox, parse_bbox
from app.domain.route import RouteResult, plan_route
from app.domain.text_parse import TextSuggestion, parse_text
from app.domain.history import HistoryEvent, build_history
from app.domain.stats import AdminStats, compute_stats
from app.domain.verification import Verification, activity_type, summarize
from app.domain.enums import (
    CurrentState,
    DecisionAction,
    FeatureKey,
    Nature,
    NeedsProfile,
    ObservationSource,
    ObservationValue,
    QueueStatus,
    Role,
    Severity,
    StateValue,
    ValidationStatus,
)
from app.domain.errors import (
    ConflictError,
    FileTooLarge,
    Forbidden,
    NotARealPlace,
    NotFound,
    Unauthorized,
    ValidationFailed,
)
from app.domain.model import (
    CheckResult,
    FeatureStateRecord,
    GeoPoint,
    ImageAnalysis,
    Observation,
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
IMAGE_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg"}


SORTS = (None, "nearest", "name", "recently_verified")
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
class GeocodeHit:
    label: str
    place_id: str
    location: GeoPoint


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


def _enum(enum_cls, value, field: str):
    try:
        return enum_cls(value)
    except ValueError as e:
        raise ValidationFailed(f"invalid {field}: {value}") from e


class UseCases:
    def __init__(self, repo: Repo, clock: Clock, ids: IdGenerator, storage: FileStorage,
                 verifier: IdentityVerifier | None, *, auth_mode: str = "demo",
                 admin_emails: list[str] | None = None, session_ttl_hours: int = 24,
                 vision: VisionAnalyzer | None = None, osm: OsmSource | None = None):
        self.repo = repo
        self.clock = clock
        self.ids = ids
        self.storage = storage
        self.verifier = verifier
        self.auth_mode = auth_mode
        self.admin_emails = admin_emails or []
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.vision = vision
        self.osm = osm

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
        user = self.repo.find_user_by_google_sub(identity.sub)
        if user is None:
            user = User(self.ids.new("usr"), identity.name or identity.email, role,
                        email=identity.email, google_sub=identity.sub)
            self.repo.add_user(user)
        else:
            user.email, user.display_name, user.role = identity.email, identity.name or user.display_name, role
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

    def _new_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        self.repo.add_session(Session(token, user.id, self.clock.now() + self.session_ttl))
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
            raise ValidationFailed(f"sort must be one of: nearest, name, recently_verified (got {query.sort})")
        if query.sort == "nearest" and query.near is None:
            raise ValidationFailed("sort=nearest needs lat and lon")
        try:
            bbox = parse_bbox(query.bbox) if query.bbox else None
        except ValueError as e:
            raise ValidationFailed(str(e)) from e

        items = []
        for p in self.search_places(query.features, query.category, query.q):
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

    def get_place(self, place_id: str) -> Place:
        place = self.repo.get_place(place_id)
        if place is None:
            raise NotFound(f"place not found: {place_id}")
        return place

    def get_accessibility(self, place_id: str) -> dict[FeatureKey, FeatureStateRecord]:
        """All MVP features; missing = unknown."""
        self.get_place(place_id)
        states = self.repo.states_for(place_id)
        return {f: states.get(f) or FeatureStateRecord(place_id, f, StateValue.UNKNOWN) for f in FeatureKey}

    def check_place(self, place_id: str, profile: NeedsProfile) -> CheckResult:
        states = self.get_accessibility(place_id)
        issues = [o for o in self.repo.list_observations(place_id)
                  if o.temporary and o.value == ObservationValue.NO
                  and o.validation != ValidationStatus.REJECTED
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

    # ------------------------------------------------------------------ OSM import (F8)
    async def import_osm(self, admin: User | None, source: str = "osm_file") -> ImportResult:
        """OSM points → open_data observations. Idempotent; matches places by external id or name ≤50 m."""
        self._require_admin(admin)
        if source != "osm_file" or self.osm is None:
            raise ValidationFailed(f"unknown import source: {source}")
        points = await self.osm.fetch()

        result = ImportResult(source, points=len(points))
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
            place = self._match_place(p)
            if place:
                result.places_matched += 1
            else:
                place = Place(self.ids.new("plc_osm"), p.name, domain_osm.map_category(p.category),
                              GeoPoint(p.lat, p.lon), "Import: OpenStreetMap", external_id=p.external_id)
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

    def _match_place(self, p: domain_osm.OsmPoint) -> Place | None:
        here = GeoPoint(p.lat, p.lon)
        for place in self.repo.list_places():
            if place.external_id == p.external_id:
                return place
            if (place.name.lower() == p.name.lower()
                    and haversine_m(place.location, here) <= domain_osm.MATCH_RADIUS_M):
                return place
        return None

    def _has_open_data(self, place_id: str, feature: FeatureKey, value: ObservationValue) -> bool:
        return any(o.source == ObservationSource.OPEN_DATA and o.value == value
                   and o.validation != ValidationStatus.REJECTED
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

    @staticmethod
    def _require_owner(user: User | None) -> None:
        if user is None:
            raise Unauthorized("login required")
        if user.role != Role.OWNER:
            raise Forbidden("owner role required")

    # ------------------------------------------------------------------ AI suggestions (F6)
    async def analyze_image(self, user: User | None, photo_ids: list[str],
                            place_id: str | None = None) -> ImageTagsResult:
        """Suggestions for the report form. Never changes feature state."""
        self._require_user(user)
        if not 1 <= len(photo_ids) <= MAX_PHOTOS:
            raise ValidationFailed(f"photo_ids: 1..{MAX_PHOTOS} required")
        photos = [self.repo.get_photo(p) for p in self._check_photos(photo_ids)]
        if place_id:
            self.get_place(place_id)
        if self.vision is None:
            raise ValidationFailed("AI is not configured")

        analyses = [await self.vision.analyze(p.path, p.original_name) for p in photos]
        real = [a for a in analyses if a.real_place]
        if not real:
            raise NotARealPlace("no photo shows a real place (screenshot or graphic?)")

        best = max(real, key=lambda a: a.confidence)
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

    # ------------------------------------------------------------------ moderation (F4)
    def list_queue(self, admin: User | None, filter: str = "all", status: str = "open") -> list[QueueItem]:
        self._require_admin(admin)
        items = self.repo.list_queue_items()
        if filter not in ("all", "conflict") or status not in ("open", "resolved", "all"):
            raise ValidationFailed("filter must be all|conflict, status open|resolved|all")
        if filter == "conflict":
            items = [q for q in items if q.type == "conflict"]
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
               winning_observation_id: str | None = None, comment: str = "") -> FeatureStateRecord:
        """confirm: winner kept + admin observation, opposite values REJECTED; reject: all REJECTED.
        Observations are never deleted — only their validation changes."""
        item = self.get_queue_item(admin, item_id)
        action_v = _enum(DecisionAction, action, "action")
        if item.status != QueueStatus.OPEN:
            raise ConflictError(f"queue item already resolved: {item_id}")
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
        return self.recompute(item.place_id, item.feature)

    # ------------------------------------------------------------------ observations (F3)
    def recompute(self, place_id: str, feature: FeatureKey) -> FeatureStateRecord:
        """observations → validation (conflict → queue) → trust → state. Sync block = atomic."""
        observations = self.repo.list_observations(place_id, feature)
        for o in observations:
            o.confidence = trust.observation_confidence(o)
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
        state = trust.compute_feature_state(place_id, feature, observations, conflict_open=item is not None)
        self.repo.save_state(state)
        return state

    async def upload_photo(self, user: User | None, chunks: AsyncIterator[bytes], filename: str) -> Photo:
        self._require_user(user)
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
        photo = Photo(photo_id, path, url, original_name=filename)
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
        value = ObservationValue.YES if report.current_state == CurrentState.WORKS else ObservationValue.NO
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
                        photo_ids: list[str] | tuple = ()) -> Observation:
        self._require_user(user)
        self.get_place(place_id)
        feature_v = _enum(FeatureKey, feature, "feature")
        value_v = _enum(ObservationValue, value, "value")
        obs = self._new_observation(user, place_id, feature_v, value_v, temporary=temporary,
                                    comment=comment, photo_ids=self._check_photos(photo_ids))
        self.recompute(place_id, feature_v)
        return obs

    def list_observations(self, place_id: str, feature: FeatureKey | None = None,
                          active: bool = True) -> list[Observation]:
        self.get_place(place_id)
        observations = self.repo.list_observations(place_id, feature)
        if active:
            observations = [o for o in observations if o.validation != ValidationStatus.REJECTED]
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
                          temporary=temporary, comment=comment, evidence_ids=list(photo_ids),
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
