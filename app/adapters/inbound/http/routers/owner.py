from fastapi import APIRouter
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, AdminUser, CurrentUser
from app.adapters.inbound.http.schemas import (
    ObservationIn,
    ObservationList,
    PlaceSummary,
    ReportOut,
    UserOut,
    observation_out,
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
    return OwnerPlaces(items=[place_summary(p, uc.yes_features(p.id)) for p in uc.list_owner_places(user)])


@router.post("/owner/places/{place_id}/observations", status_code=201, response_model=ObservationList,
             tags=["owner"])
async def add_owner_observations(place_id: str, body: OwnerObservationsIn, uc: UC, user: CurrentUser):
    created = uc.add_owner_observations(user, place_id, [o.model_dump() for o in body.observations])
    return ObservationList(items=[observation_out(uc, o, user) for o in created])


@router.get("/owner/reports", response_model=OwnerReports, tags=["owner"])
async def list_owner_reports(uc: UC, user: CurrentUser):
    return OwnerReports(items=[report_out(uc, r) for r in uc.list_owner_reports(user)])


@router.post("/admin/places/{place_id}/owner", response_model=AssignOwnerOut, tags=["admin"])
async def assign_owner(place_id: str, body: AssignOwnerIn, uc: UC, admin: AdminUser):
    place = uc.assign_owner(admin, place_id, body.user_id)
    return AssignOwnerOut(place_id=place.id, owner=user_out(uc.repo.get_user(place.owner_id)))
