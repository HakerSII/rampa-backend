import re
from collections import defaultdict
from datetime import datetime, timezone

from app.domain.enums import FeatureKey
from app.domain.model import (
    LoginToken,
    Notification,
    Question,
    FeatureStateRecord,
    Observation,
    OwnershipRequest,
    Photo,
    Place,
    QueueItem,
    Report,
    Session,
    User,
)


class InMemoryRepo:
    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.users: dict[str, User] = {}
        self.sessions: dict[str, Session] = {}
        self.login_tokens: dict[str, LoginToken] = {}
        self.questions: dict[str, Question] = {}
        self.notifications: dict[str, Notification] = {}
        self.places: dict[str, Place] = {}
        self.states: dict[str, dict[FeatureKey, FeatureStateRecord]] = defaultdict(dict)
        self.observations: dict[str, Observation] = {}  # insertion order = creation order
        self.reports: dict[str, Report] = {}
        self.photos: dict[str, Photo] = {}
        self.queue: dict[str, QueueItem] = {}
        self.ownership_requests: dict[str, OwnershipRequest] = {}

    def commit(self) -> None:
        """Nothing to persist."""

    def reload_if_stale(self) -> bool:
        return False  # single process, memory is the only copy

    def is_empty(self) -> bool:
        return not self.users

    def all_ids(self) -> list[str]:
        return [*self.users, *self.places, *self.observations, *self.reports, *self.photos, *self.queue,
                *self.ownership_requests, *self.questions, *self.notifications]

    # users / sessions
    def add_user(self, user: User) -> None:
        self.users[user.id] = user

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def find_user_by_username(self, username: str) -> User | None:
        return next((u for u in self.users.values() if u.username == username), None)

    def find_user_by_google_sub(self, sub: str) -> User | None:
        return next((u for u in self.users.values() if u.google_sub == sub), None)

    def find_user_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email and u.email.lower() == email.lower()), None)

    def add_login_token(self, token: LoginToken) -> None:
        self.login_tokens[token.token_hash] = token

    def get_login_token(self, token_hash: str) -> LoginToken | None:
        return self.login_tokens.get(token_hash)

    def list_login_tokens(self, email: str) -> list[LoginToken]:
        return [t for t in self.login_tokens.values() if t.email == email]

    def add_session(self, session: Session) -> None:
        self.sessions[session.token] = session

    def get_session(self, token: str) -> Session | None:
        return self.sessions.get(token)

    def delete_session(self, token: str) -> None:
        self.sessions.pop(token, None)

    # places / states
    def add_place(self, place: Place) -> None:
        self.places[place.id] = place

    def get_place(self, place_id: str) -> Place | None:
        return self.places.get(place_id)

    def list_places(self) -> list[Place]:
        return list(self.places.values())

    def delete_place(self, place_id: str) -> None:
        self.places.pop(place_id, None)
        self.states.pop(place_id, None)

    def save_state(self, state: FeatureStateRecord) -> None:
        self.states[state.place_id][state.feature] = state

    def states_for(self, place_id: str) -> dict[FeatureKey, FeatureStateRecord]:
        return dict(self.states.get(place_id, {}))

    # observations / reports / photos
    def add_observation(self, obs: Observation) -> None:
        self.observations[obs.id] = obs

    def get_observation(self, obs_id: str) -> Observation | None:
        return self.observations.get(obs_id)

    def list_observations(self, place_id: str, feature: FeatureKey | None = None) -> list[Observation]:
        return [
            o for o in self.observations.values()
            if o.place_id == place_id and (feature is None or o.feature == feature)
        ]

    def add_report(self, report: Report) -> None:
        self.reports[report.id] = report

    def get_report(self, report_id: str) -> Report | None:
        return self.reports.get(report_id)

    def list_reports(self) -> list[Report]:
        return list(self.reports.values())

    def add_photo(self, photo: Photo) -> None:
        self.photos[photo.id] = photo

    def get_photo(self, photo_id: str) -> Photo | None:
        return self.photos.get(photo_id)

    def delete_photo(self, photo_id: str) -> None:
        self.photos.pop(photo_id, None)

    # moderation queue
    def add_queue_item(self, item: QueueItem) -> None:
        self.queue[item.id] = item

    def get_queue_item(self, item_id: str) -> QueueItem | None:
        return self.queue.get(item_id)

    def list_queue_items(self) -> list[QueueItem]:
        return list(self.queue.values())

    def find_open_queue_item(self, place_id: str, feature: FeatureKey) -> QueueItem | None:
        return next(
            (q for q in self.queue.values()
             if q.place_id == place_id and q.feature == feature and q.open_conflict),
            None,
        )


    # ownership requests
    def add_notification(self, n: Notification) -> None:
        self.notifications[n.id] = n

    def list_notifications(self, user_id: str) -> list[Notification]:
        return [n for n in self.notifications.values() if n.user_id == user_id]

    def add_question(self, q: Question) -> None:
        self.questions[q.id] = q

    def get_question(self, question_id: str) -> Question | None:
        return self.questions.get(question_id)

    def list_questions(self) -> list[Question]:
        return list(self.questions.values())

    def add_ownership_request(self, req: OwnershipRequest) -> None:
        self.ownership_requests[req.id] = req

    def get_ownership_request(self, req_id: str) -> OwnershipRequest | None:
        return self.ownership_requests.get(req_id)

    def list_ownership_requests(self) -> list[OwnershipRequest]:
        return list(self.ownership_requests.values())


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now


class SeqIdGenerator:
    """Deterministic ids: obs_1, obs_2, … (per prefix)."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)

    def new(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}_{self._counters[prefix]}"

    def observe(self, existing_id: str) -> None:
        if m := re.fullmatch(r"(.+)_(\d+)", existing_id):
            prefix, n = m.group(1), int(m.group(2))
            self._counters[prefix] = max(self._counters[prefix], n)
