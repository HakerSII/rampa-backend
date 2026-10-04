from fastapi import APIRouter, Form, Response, UploadFile

from app.adapters.inbound.http.deps import UC, CurrentUser, OptionalUser
from app.adapters.inbound.http.schemas import (
    AbuseIn,
    QueueItemOut,
    queue_item_out,
    Location,
    MapObservationOut,
    MapObservations,
    MapPlaceOut,
    ObservationIn,
    ObservationList,
    ObservationOut,
    PhotoOut,
    ReportIn,
    ReportOut,
    ReportPatchIn,
    VoteIn,
    VoteResultOut,
    feature_state_out,
    observation_out,
    photo_out,
    report_out,
)
from app.domain.enums import FeatureKey

router = APIRouter()

CHUNK = 64 * 1024


async def read_chunks(file: UploadFile):
    while chunk := await file.read(CHUNK):
        yield chunk


@router.post("/uploads", status_code=201, response_model=PhotoOut, tags=["media"])
async def upload_photo(file: UploadFile, uc: UC, user: CurrentUser, place_id: str | None = Form(None),
                       element: str | None = Form(None), current_state: str | None = Form(None)):
    """Optional metadata (F45): what the user says the photo shows; the AI check confirms it."""
    photo = await uc.upload_photo(user, read_chunks(file), file.filename or "upload",
                                  place_id=place_id, element=element, current_state=current_state)
    return photo_out(photo)


@router.post("/reports", status_code=201, response_model=ReportOut, tags=["reports"])
async def create_report(body: ReportIn, uc: UC, user: CurrentUser):
    return report_out(uc, uc.create_report(user, **body.model_dump()))


@router.patch("/reports/{report_id}", response_model=ReportOut, tags=["reports"])
async def update_report(report_id: str, body: ReportPatchIn, uc: UC, user: CurrentUser):
    """Edit a draft (author only)."""
    return report_out(uc, uc.update_report(user, report_id, **body.model_dump(exclude_unset=True)))


@router.post("/reports/{report_id}/submit", response_model=ReportOut, tags=["reports"])
async def submit_report(report_id: str, uc: UC, user: CurrentUser):
    """Draft → submitted: full validation, creates the observation."""
    return report_out(uc, uc.submit_report(user, report_id))


@router.get("/reports/{report_id}", response_model=ReportOut, tags=["reports"])
async def get_report(report_id: str, uc: UC, user: CurrentUser):
    return report_out(uc, uc.get_report(user, report_id))


@router.get("/observations", response_model=MapObservations, tags=["observations"])
async def map_observations(uc: UC, me: OptionalUser, bbox: str | None = None, active: bool = True,
                           feature: str | None = None, value: str | None = None, current: bool = False,
                           since: str | None = None, limit: int = 200):
    """F24 map layer: observations across places (one request), newest first, with place + report severity."""
    rows = uc.map_observations(bbox=bbox, active=active, feature=feature, value=value, current=current,
                               since=since, limit=limit)
    items = [MapObservationOut(**observation_out(uc, o, me).model_dump(),
                               place=MapPlaceOut(id=p.id, name=p.name,
                                                 location=Location(lat=p.location.lat, lon=p.location.lon)),
                               severity=sev) for o, p, sev in rows]
    return MapObservations(items=items, total=len(items))


@router.get("/places/{place_id}/observations", response_model=ObservationList, tags=["observations"])
async def list_observations(place_id: str, uc: UC, me: OptionalUser,
                            feature: FeatureKey | None = None, active: bool = True):
    items = uc.list_observations(place_id, feature, active)
    return ObservationList(items=[observation_out(uc, o, me) for o in items])


@router.post("/places/{place_id}/observations", status_code=201, response_model=ObservationOut,
             tags=["observations"])
async def add_observation(place_id: str, body: ObservationIn, uc: UC, user: CurrentUser):
    return observation_out(uc, uc.add_observation(user, place_id, **body.model_dump()), user)


@router.post("/observations/{observation_id}/votes", response_model=VoteResultOut, tags=["observations"])
async def vote(observation_id: str, body: VoteIn, uc: UC, user: CurrentUser):
    obs, state = uc.vote(user, observation_id, body.value)
    return VoteResultOut(observation=observation_out(uc, obs, user), feature_state=feature_state_out(state))


@router.post("/observations/{observation_id}/abuse", status_code=201, response_model=QueueItemOut,
             tags=["observations"])
async def report_abuse(observation_id: str, body: AbuseIn, uc: UC, user: CurrentUser):
    """F26: report spam / false data → admin moderation queue (type abuse)."""
    return queue_item_out(uc, uc.report_abuse(user, observation_id, body.reason))


@router.delete("/observations/{observation_id}/votes/me", status_code=204, tags=["observations"])
async def remove_vote(observation_id: str, uc: UC, user: CurrentUser):
    uc.remove_vote(user, observation_id)
    return Response(status_code=204)
