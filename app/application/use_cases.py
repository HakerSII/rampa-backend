"""All MVP use cases (application layer). Depends only on domain + ports."""
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

from app.application.ports import Clock, FileStorage, IdentityVerifier, IdGenerator, Repo, VisionAnalyzer
from app.domain import check as domain_check, suggestions, trust, validation
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
    ImageAnalysis,
    Observation,
    Photo,
    Place,
    QueueItem,
    Report,
    Session,
    User,
)
from app.seed import load_seed

DEMO_TOKEN_PREFIX = "demo-"
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTOS = 5
MAX_DESCRIPTION = 1000
IMAGE_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg"}


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
                 vision: VisionAnalyzer | None = None):
        self.repo = repo
        self.clock = clock
        self.ids = ids
        self.storage = storage
        self.verifier = verifier
        self.auth_mode = auth_mode
        self.admin_emails = admin_emails or []
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.vision = vision

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

    def yes_features(self, place_id: str) -> list[FeatureKey]:
        return [f for f, s in self.repo.states_for(place_id).items() if s.state == StateValue.YES]

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
            item.status, item.decision = QueueStatus.RESOLVED, "approved"
            self._new_observation(admin, item.place_id, item.feature, winner.value, temporary=winner.temporary,
                                  comment=comment or "Potwierdzone przez moderatora", photo_ids=[])
        else:
            for o in observations:
                o.validation = ValidationStatus.REJECTED
            item.status, item.decision = QueueStatus.RESOLVED, "rejected"
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

    def create_report(self, user: User | None, *, place_id: str, element: str, current_state: str,
                      severity: str, nature: str, description: str,
                      photo_ids: list[str] | tuple = ()) -> Report:
        """MVP: report is submitted immediately and creates one observation."""
        self._require_user(user)
        self.get_place(place_id)
        feature = _enum(FeatureKey, element, "element")
        state = _enum(CurrentState, current_state, "current_state")
        severity_v = _enum(Severity, severity, "severity")
        nature_v = _enum(Nature, nature, "nature")
        if not 1 <= len(description.strip()) <= MAX_DESCRIPTION:
            raise ValidationFailed(f"description must have 1..{MAX_DESCRIPTION} characters")
        photo_ids = self._check_photos(photo_ids)

        report = Report(self.ids.new("rep"), place_id, user.id, feature, state, severity_v, nature_v,
                        description.strip(), self.clock.now(), photo_ids=photo_ids)
        value = ObservationValue.YES if state == CurrentState.WORKS else ObservationValue.NO
        obs = self._new_observation(user, place_id, feature, value, temporary=nature_v == Nature.TEMPORARY,
                                    comment=report.description, photo_ids=photo_ids, report_id=report.id)
        report.observation_ids = [obs.id]
        self.repo.add_report(report)
        self.recompute(place_id, feature)
        return report

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
                         report_id: str | None = None) -> Observation:
        source = ObservationSource.ADMIN if user.role == Role.ADMIN else ObservationSource.COMMUNITY
        obs = Observation(self.ids.new("obs"), place_id, feature, value, source, user.id, self.clock.now(),
                          temporary=temporary, comment=comment, evidence_ids=list(photo_ids),
                          report_id=report_id)
        self.repo.add_observation(obs)
        return obs

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
