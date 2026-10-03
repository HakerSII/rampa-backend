from fastapi import APIRouter, Response, UploadFile

from app.adapters.inbound.http.deps import UC, CurrentUser, OptionalUser
from app.adapters.inbound.http.schemas import (
    ObservationIn,
    ObservationList,
    ObservationOut,
    PhotoOut,
    ReportIn,
    ReportOut,
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
async def upload_photo(file: UploadFile, uc: UC, user: CurrentUser):
    photo = await uc.upload_photo(user, read_chunks(file), file.filename or "upload")
    return photo_out(photo)


@router.post("/reports", status_code=201, response_model=ReportOut, tags=["reports"])
async def create_report(body: ReportIn, uc: UC, user: CurrentUser):
    return report_out(uc, uc.create_report(user, **body.model_dump()))


@router.get("/reports/{report_id}", response_model=ReportOut, tags=["reports"])
async def get_report(report_id: str, uc: UC, user: CurrentUser):
    return report_out(uc, uc.get_report(user, report_id))


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


@router.delete("/observations/{observation_id}/votes/me", status_code=204, tags=["observations"])
async def remove_vote(observation_id: str, uc: UC, user: CurrentUser):
    uc.remove_vote(user, observation_id)
    return Response(status_code=204)
