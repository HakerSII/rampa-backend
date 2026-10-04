import json
from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, AdminUser, OptionalUser
from app.domain.errors import ValidationFailed
from app.adapters.inbound.http.schemas import (
    DecisionIn,
    DecisionOut,
    ObservationOut,
    OwnershipRequestOut,
    QueueCommentOut,
    QueueDetailOut,
    QueuePage,
    author_out,
    observation_out,
    ownership_out,
    feature_state_out,
    queue_detail_out,
    queue_item_out,
)

router = APIRouter(tags=["admin"])



@router.get("/admin/queue", response_model=QueuePage)
async def list_queue(uc: UC, admin: AdminUser, filter: str = "all", status: str = "open"):
    items = uc.list_queue(admin, filter, status)
    open_items = uc.list_queue(admin, "all", "open")
    counts = {"all": len(open_items), "conflict": sum(q.type == "conflict" for q in open_items),
              "abuse": sum(q.type == "abuse" for q in open_items),
              "new_place": sum(q.type == "new_place" for q in open_items)}
    return QueuePage(items=[queue_item_out(uc, q) for q in items], total=len(items), counts=counts)


@router.get("/admin/queue/{item_id}", response_model=QueueDetailOut)
async def get_queue_item(item_id: str, uc: UC, admin: AdminUser):
    return queue_detail_out(uc, uc.get_queue_item(admin, item_id), admin)


@router.post("/admin/queue/{item_id}/decision", response_model=DecisionOut)
async def decide(item_id: str, body: DecisionIn, uc: UC, admin: AdminUser):
    state = uc.decide(admin, item_id, body.action, body.winning_observation_id, body.comment)
    item = uc.get_queue_item(admin, item_id)
    return DecisionOut(id=item.id, status=item.decision, feature_state=feature_state_out(state) if state else None)


class StatTileOut(BaseModel):
    value: int
    change_pct: float | None


class AdminStatsOut(BaseModel):
    new_reports_today: StatTileOut
    data_conflicts: StatTileOut
    low_confidence: StatTileOut
    observations_today: StatTileOut
    abuse_flags: StatTileOut
    places: StatTileOut
    updated_at: str


@router.get("/admin/stats", response_model=AdminStatsOut)
async def admin_stats(uc: UC, admin: AdminUser):
    """Dashboard tiles: value + change vs yesterday (%)."""
    s = uc.admin_stats(admin)
    tile = lambda t: StatTileOut(value=t.value, change_pct=t.change_pct)  # noqa: E731
    return AdminStatsOut(new_reports_today=tile(s.new_reports_today), data_conflicts=tile(s.data_conflicts),
                         low_confidence=tile(s.low_confidence), observations_today=tile(s.observations_today),
                         abuse_flags=tile(s.abuse_flags),
                         places=tile(s.places), updated_at=s.updated_at.isoformat())


@router.post("/admin/demo/reset", status_code=204)
async def reset_demo(uc: UC, user: OptionalUser):
    uc.reset_demo(user)  # use case enforces admin (401/403)
    return Response(status_code=204)


class ImportIn(BaseModel):
    source: str


class ImportOut(BaseModel):
    source: str
    points: int
    places_created: int
    places_matched: int
    observations: int
    skipped_unnamed: int
    skipped_no_data: int


def _load_catalog(path: str) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValidationFailed(f"catalog file not readable: {path}") from e
    if not isinstance(data, list):
        raise ValidationFailed("catalog file must be a JSON list")
    return data


@router.post("/admin/imports", response_model=ImportOut)
async def run_import(body: ImportIn, uc: UC, admin: AdminUser, request: Request):
    """source: osm_file (snapshot) | overpass (live) | catalog (F49: CATALOG_FILE, the full place catalogue)."""
    if body.source == "catalog":
        r = await uc.import_catalog(admin, _load_catalog(request.app.state.settings.catalog_file))
    else:
        r = await uc.import_osm(admin, body.source)
    return ImportOut(**{f: getattr(r, f) for f in ImportOut.model_fields})


# ---------------------------------------------------------------- admin extras (F21)
class ConfidenceOut(BaseModel):
    overall: float
    by_group: dict[str, float]
    note: str


@router.get("/admin/places/{place_id}/confidence", response_model=ConfidenceOut)
async def place_confidence(place_id: str, uc: UC, admin: AdminUser):
    """Widget "Pewność danych": mean confidence overall and per group (known features)."""
    c = uc.place_confidence(admin, place_id)
    return ConfidenceOut(overall=c.overall, by_group=c.by_group, note=c.note)


class CommentIn(BaseModel):
    text: str


@router.post("/admin/queue/{item_id}/comments", status_code=201, response_model=list[QueueCommentOut])
async def add_queue_comment(item_id: str, body: CommentIn, uc: UC, admin: AdminUser):
    item = uc.add_queue_comment(admin, item_id, body.text)
    return [QueueCommentOut(author=author_out(uc, c["author_id"]), text=c["text"], created_at=c["created_at"])
            for c in item.comments]


class FlagIn(BaseModel):
    reason: str


@router.post("/admin/observations/{observation_id}/flag", response_model=ObservationOut)
async def flag_observation(observation_id: str, body: FlagIn, uc: UC, admin: AdminUser):
    """Abuse / spam → FLAGGED: excluded from trust and conflicts, history kept."""
    return observation_out(uc, uc.flag_observation(admin, observation_id, body.reason), admin)


class MergeIn(BaseModel):
    into_place_id: str


class MergeOut(BaseModel):
    merged: str
    into_place_id: str


@router.post("/admin/places/{place_id}/merge", response_model=MergeOut)
async def merge_places(place_id: str, body: MergeIn, uc: UC, admin: AdminUser):
    """Duplicate → target (observations, reports, queue, favourites moved; duplicate deleted)."""
    target = uc.merge_places(admin, place_id, body.into_place_id)
    return MergeOut(merged=place_id, into_place_id=target.id)


class RevalidateOut(BaseModel):
    places: int
    features: int


@router.post("/admin/revalidate", response_model=RevalidateOut)
async def revalidate(uc: UC, admin: AdminUser):
    return RevalidateOut(**uc.revalidate(admin))


class OwnershipRequests(BaseModel):
    items: list[OwnershipRequestOut]


class VerifyIn(BaseModel):
    approved: bool = True


@router.get("/admin/ownership-requests", response_model=OwnershipRequests)
async def list_ownership_requests(uc: UC, admin: AdminUser, status: str = "pending"):
    return OwnershipRequests(items=[ownership_out(uc, r) for r in uc.list_ownership_requests(admin, status)])


@router.post("/admin/ownership-requests/{request_id}/verify", response_model=OwnershipRequestOut)
async def verify_ownership(request_id: str, body: VerifyIn, uc: UC, admin: AdminUser):
    """approved=true → user becomes owner of the place."""
    return ownership_out(uc, uc.verify_ownership(admin, request_id, body.approved))


# ---------------------------------------------------------------- F36 insights
class ActivityCellOut(BaseModel):
    lat: float
    lon: float
    observations: int
    reports: int


class ActivityOut(BaseModel):
    cell_deg: float
    days: int
    cells: list[ActivityCellOut]


class TrendDayOut(BaseModel):
    day: str
    observations: int
    reports: int
    questions: int
    queue_items: int


class TrendsOut(BaseModel):
    days: list[TrendDayOut]


class CategoryCoverageOut(BaseModel):
    category: str
    places: int
    with_data: int
    avg_known_features: float


class MissingFeatureOut(BaseModel):
    feature: str
    label: str
    places_without_data: int


class CoverageOut(BaseModel):
    categories: list[CategoryCoverageOut]
    most_missing: list[MissingFeatureOut]


@router.get("/admin/activity", response_model=ActivityOut)
async def activity(uc: UC, admin: AdminUser, days: int = 30, cell_deg: float = 0.005, bbox: str | None = None):
    """Activity map: observations + reports per grid cell (cell centres, busiest first)."""
    cells = uc.admin_activity(admin, days, cell_deg, bbox)
    return ActivityOut(cell_deg=cell_deg, days=days, cells=[ActivityCellOut(**{f: getattr(c, f) for f in
                                                                              ActivityCellOut.model_fields})
                                                            for c in cells])


@router.get("/admin/trends", response_model=TrendsOut)
async def trends(uc: UC, admin: AdminUser, days: int = 30):
    return TrendsOut(days=[TrendDayOut(**{f: getattr(d, f) for f in TrendDayOut.model_fields})
                           for d in uc.admin_trends(admin, days)])


@router.get("/admin/coverage", response_model=CoverageOut)
async def coverage(uc: UC, admin: AdminUser):
    """Data coverage per category + core features most often missing."""
    from app.domain.enums import LABELS_PL
    c = uc.admin_coverage(admin)
    return CoverageOut(
        categories=[CategoryCoverageOut(**{f: getattr(x, f) for f in CategoryCoverageOut.model_fields})
                    for x in c.categories],
        most_missing=[MissingFeatureOut(feature=f, label=LABELS_PL[f], places_without_data=n) for f, n in c.most_missing])
