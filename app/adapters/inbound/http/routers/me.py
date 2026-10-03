from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, CurrentUser
from app.adapters.inbound.http.schemas import PlaceSummary, ReportOut, place_summary, report_out

router = APIRouter(tags=["me"])


class Favorites(BaseModel):
    items: list[PlaceSummary]


class MyReports(BaseModel):
    items: list[ReportOut]


@router.get("/me/favorites", response_model=Favorites)
async def list_favorites(uc: UC, user: CurrentUser):
    return Favorites(items=[place_summary(p, uc.yes_features(p.id), uc.verification_for(p.id))
                            for p in uc.list_favorites(user)])


@router.put("/me/favorites/{place_id}", status_code=204)
async def add_favorite(place_id: str, uc: UC, user: CurrentUser):
    uc.add_favorite(user, place_id)
    return Response(status_code=204)


@router.delete("/me/favorites/{place_id}", status_code=204)
async def remove_favorite(place_id: str, uc: UC, user: CurrentUser):
    uc.remove_favorite(user, place_id)
    return Response(status_code=204)


@router.get("/me/reports", response_model=MyReports)
async def my_reports(uc: UC, user: CurrentUser):
    return MyReports(items=[report_out(uc, r) for r in uc.my_reports(user)])
