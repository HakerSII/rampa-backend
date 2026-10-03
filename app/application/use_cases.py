"""All MVP use cases (application layer). Depends only on domain + ports."""
import secrets
from collections.abc import AsyncIterator
from datetime import timedelta

from app.application.ports import Clock, FileStorage, IdentityVerifier, IdGenerator, Repo
from app.domain import check as domain_check, trust, validation
from app.domain.enums import (
    CurrentState,
    FeatureKey,
    Nature,
    NeedsProfile,
    ObservationSource,
    ObservationValue,
    Role,
    Severity,
    StateValue,
    ValidationStatus,
)
from app.domain.errors import FileTooLarge, Forbidden, NotFound, Unauthorized, ValidationFailed
from app.domain.model import (
    CheckResult,
    FeatureStateRecord,
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


def _enum(enum_cls, value, field: str):
    try:
        return enum_cls(value)
    except ValueError as e:
        raise ValidationFailed(f"invalid {field}: {value}") from e


class UseCases:
    def __init__(self, repo: Repo, clock: Clock, ids: IdGenerator, storage: FileStorage,
                 verifier: IdentityVerifier | None, *, auth_mode: str = "demo",
                 admin_emails: list[str] | None = None, session_ttl_hours: int = 24):
        self.repo = repo
        self.clock = clock
        self.ids = ids
        self.storage = storage
        self.verifier = verifier
        self.auth_mode = auth_mode
        self.admin_emails = admin_emails or []
        self.session_ttl = timedelta(hours=session_ttl_hours)

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
        photo = Photo(photo_id, path, url)
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
