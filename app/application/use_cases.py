"""All MVP use cases (application layer). Depends only on domain + ports."""
import secrets
from datetime import timedelta

from app.application.ports import Clock, FileStorage, IdentityVerifier, IdGenerator, Repo
from app.domain import check as domain_check
from app.domain.enums import (
    FeatureKey,
    NeedsProfile,
    ObservationValue,
    Role,
    StateValue,
    ValidationStatus,
)
from app.domain.errors import Forbidden, NotFound, Unauthorized
from app.domain.model import CheckResult, FeatureStateRecord, Place, Session, User
from app.seed import load_seed

DEMO_TOKEN_PREFIX = "demo-"


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

    # ------------------------------------------------------------------ state
    def recompute(self, place_id: str, feature: FeatureKey) -> FeatureStateRecord:
        """F0 stub: state = latest observation value. Replaced by trust engine in F3."""
        observations = self.repo.list_observations(place_id, feature)
        if not observations:
            state = FeatureStateRecord(place_id, feature, StateValue.UNKNOWN)
        else:
            latest = observations[-1]
            state = FeatureStateRecord(place_id, feature, StateValue(latest.value),
                                       last_verified=latest.created_at,
                                       active_observation_id=latest.id)
        self.repo.save_state(state)
        return state
