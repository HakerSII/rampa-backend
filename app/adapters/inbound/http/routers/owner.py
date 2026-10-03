from fastapi import APIRouter, Response, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, AdminUser, CurrentUser
from app.domain.enums import FeatureKey
from app.adapters.inbound.http.schemas import (
    ObservationIn,
    ObservationList,
    ObservationOut,
    PlaceOut,
    OwnershipRequestOut,
    PlaceSummary,
    ReportOut,
    UserOut,
    observation_out,
    ownership_out,
    place_out,
    place_summary,
    report_out,
    user_out,
)

router = APIRouter()


class OwnerPlaces(BaseModel):
    items: list[PlaceSummary]


class OwnerObservationsIn(BaseModel):
    observations: list[ObservationIn]


class OwnerReports(BaseModel):
    items: list[ReportOut]


class AssignOwnerIn(BaseModel):
    user_id: str


class AssignOwnerOut(BaseModel):
    place_id: str
    owner: UserOut


@router.get("/owner/places", response_model=OwnerPlaces, tags=["owner"])
async def list_owner_places(uc: UC, user: CurrentUser):
    return OwnerPlaces(items=[place_summary(p, uc.yes_features(p.id), uc.verification_for(p.id))
                              for p in uc.list_owner_places(user)])


@router.post("/owner/places/{place_id}/observations", status_code=201, response_model=ObservationList,
             tags=["owner"])
async def add_owner_observations(place_id: str, body: OwnerObservationsIn, uc: UC, user: CurrentUser):
    created = uc.add_owner_observations(user, place_id, [o.model_dump() for o in body.observations])
    return ObservationList(items=[observation_out(uc, o, user) for o in created])


@router.get("/owner/reports", response_model=OwnerReports, tags=["owner"])
async def list_owner_reports(uc: UC, user: CurrentUser):
    return OwnerReports(items=[report_out(uc, r) for r in uc.list_owner_reports(user)])


class OwnershipRequestIn(BaseModel):
    place_id: str
    justification: str = ""


@router.post("/owner/ownership-requests", status_code=201, response_model=OwnershipRequestOut, tags=["owner"])
async def request_ownership(body: OwnershipRequestIn, uc: UC, user: CurrentUser):
    """"Jestem właścicielem" — any logged-in user applies; an admin verifies."""
    return ownership_out(uc, uc.request_ownership(user, body.place_id, body.justification))


@router.post("/admin/places/{place_id}/owner", response_model=AssignOwnerOut, tags=["admin"])
async def assign_owner(place_id: str, body: AssignOwnerIn, uc: UC, admin: AdminUser):
    place = uc.assign_owner(admin, place_id, body.user_id)
    return AssignOwnerOut(place_id=place.id, owner=user_out(uc.repo.get_user(place.owner_id)))


# ---------------------------------------------------------------- owner extras (F22)
class OwnerProfileOut(BaseModel):
    id: str
    display_name: str
    email: str | None
    role: str
    verified: bool
    places: int


class OwnerProfileIn(BaseModel):
    display_name: str | None = None
    email: str | None = None


def _profile(p) -> OwnerProfileOut:
    return OwnerProfileOut(id=p.id, display_name=p.display_name, email=p.email, role=p.role, verified=p.verified,
                           places=p.places)


@router.get("/owner/me", response_model=OwnerProfileOut, tags=["owner"])
async def owner_me(uc: UC, user: CurrentUser):
    return _profile(uc.owner_profile(user))


@router.patch("/owner/me", response_model=OwnerProfileOut, tags=["owner"])
async def update_owner_me(body: OwnerProfileIn, uc: UC, user: CurrentUser):
    return _profile(uc.update_owner_profile(user, **body.model_dump(exclude_unset=True)))


class OwnerStatsOut(BaseModel):
    managed_places: int
    avg_confidence: float
    reports_30d: int
    updates_30d: int
    open_conflicts: int


@router.get("/owner/stats", response_model=OwnerStatsOut, tags=["owner"])
async def owner_stats(uc: UC, user: CurrentUser):
    s = uc.owner_stats(user)
    return OwnerStatsOut(managed_places=s.managed_places, avg_confidence=s.avg_confidence, reports_30d=s.reports_30d,
                         updates_30d=s.updates_30d, open_conflicts=s.open_conflicts)


class PlaceEditIn(BaseModel):
    name: str | None = None
    short_description: str | None = None
    address: str | None = None
    category: str | None = None
    contact: dict | None = None


@router.patch("/owner/places/{place_id}", response_model=PlaceOut, tags=["owner"])
async def edit_place(place_id: str, body: PlaceEditIn, uc: UC, user: CurrentUser):
    place = uc.update_owner_place(user, place_id, **body.model_dump(exclude_unset=True))
    return place_out(place, uc.yes_features(place.id), uc.verification_for(place.id))


class OpeningHoursEntry(BaseModel):
    days: str
    open: str | None = None
    close: str | None = None
    closed: bool = False


@router.put("/owner/places/{place_id}/opening-hours", response_model=list[dict], tags=["owner"])
async def set_opening_hours(place_id: str, body: list[OpeningHoursEntry], uc: UC, user: CurrentUser):
    return uc.set_opening_hours(user, place_id, [h.model_dump() for h in body]).opening_hours


class PlacePhotoIn(BaseModel):
    photo_id: str


@router.post("/owner/places/{place_id}/photos", status_code=201, tags=["owner"])
async def add_place_photo(place_id: str, body: PlacePhotoIn, uc: UC, user: CurrentUser):
    return {"photo_ids": uc.add_place_photo(user, place_id, body.photo_id).photo_ids}


@router.delete("/owner/places/{place_id}/photos/{photo_id}", status_code=204, tags=["owner"])
async def remove_place_photo(place_id: str, photo_id: str, uc: UC, user: CurrentUser):
    uc.remove_place_photo(user, place_id, photo_id)
    return Response(status_code=204)


class PlaceStatsOut(BaseModel):
    observations: int
    by_source: dict[str, int]
    votes_up: int
    votes_down: int
    open_conflicts: int
    last_verified: str | None
    confidence: float


@router.get("/owner/places/{place_id}/stats", response_model=PlaceStatsOut, tags=["owner"])
async def owner_place_stats(place_id: str, uc: UC, user: CurrentUser):
    s = uc.owner_place_stats(user, place_id)
    return PlaceStatsOut(observations=s.observations, by_source=s.by_source, votes_up=s.votes_up,
                         votes_down=s.votes_down, open_conflicts=s.open_conflicts,
                         last_verified=s.last_verified.isoformat() if s.last_verified else None,
                         confidence=s.confidence)


class ReplyIn(BaseModel):
    text: str


@router.post("/owner/reports/{report_id}/reply", status_code=201, response_model=ReportOut, tags=["owner"])
async def reply_to_report(report_id: str, body: ReplyIn, uc: UC, user: CurrentUser):
    return report_out(uc, uc.reply_to_report(user, report_id, body.text))


@router.post("/owner/reports/{report_id}/approve", response_model=ObservationOut, tags=["owner"])
async def approve_report(report_id: str, uc: UC, user: CurrentUser):
    """Owner confirms the report → verified_owner observation with the same value."""
    return observation_out(uc, uc.approve_report(user, report_id), user)


class ReminderOut(BaseModel):
    place_id: str
    kind: str
    text: str
    priority: str
    feature: FeatureKey | None


@router.get("/owner/reminders", tags=["owner"])
async def owner_reminders(uc: UC, user: CurrentUser) -> dict[str, list[ReminderOut]]:
    return {"items": [ReminderOut(place_id=r.place_id, kind=r.kind, text=r.text, priority=r.priority,
                                  feature=r.feature) for r in uc.owner_reminders(user)]}


class OwnerSuggestionOut(BaseModel):
    place_id: str
    feature: FeatureKey
    text: str


@router.get("/owner/suggestions", tags=["owner"])
async def owner_suggestions(uc: UC, user: CurrentUser) -> dict[str, list[OwnerSuggestionOut]]:
    return {"items": [OwnerSuggestionOut(place_id=x.place_id, feature=x.feature, text=x.text)
                      for x in uc.owner_suggestions(user)]}


class BatchItemIn(ObservationIn):
    place_id: str


@router.post("/owner/observations/batch", status_code=201, response_model=ObservationList, tags=["owner"])
async def owner_batch(body: list[BatchItemIn], uc: UC, user: CurrentUser):
    """Several own places at once; all-or-nothing."""
    created = uc.owner_batch(user, [b.model_dump() for b in body])
    return ObservationList(items=[observation_out(uc, o, user) for o in created])


@router.get("/owner/places/import/template", response_class=PlainTextResponse, tags=["owner"])
async def csv_template(uc: UC, user: CurrentUser):
    uc.owner_profile(user)  # owner only
    return PlainTextResponse(uc.owner_csv_template(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="rampa-import.csv"'})


class CsvImportOut(BaseModel):
    imported: int
    errors: list[dict]


@router.post("/owner/places/import", response_model=CsvImportOut, tags=["owner"])
async def csv_import(file: UploadFile, uc: UC, user: CurrentUser):
    """Bulk update from CSV: valid rows imported, errors listed with file line numbers."""
    text = (await file.read(1_000_000)).decode("utf-8-sig", errors="replace")
    r = uc.owner_csv_import(user, text)
    return CsvImportOut(imported=r.imported, errors=r.errors)
