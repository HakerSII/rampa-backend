from fastapi import APIRouter, Response

from app.adapters.inbound.http.deps import UC, AdminUser, OptionalUser
from app.adapters.inbound.http.schemas import (
    DecisionIn,
    DecisionOut,
    QueueDetailOut,
    QueuePage,
    feature_state_out,
    queue_detail_out,
    queue_item_out,
)

router = APIRouter(tags=["admin"])


@router.get("/admin/queue", response_model=QueuePage)
async def list_queue(uc: UC, admin: AdminUser, filter: str = "all", status: str = "open"):
    items = uc.list_queue(admin, filter, status)
    open_items = uc.list_queue(admin, "all", "open")
    counts = {"all": len(open_items), "conflict": sum(q.type == "conflict" for q in open_items)}
    return QueuePage(items=[queue_item_out(uc, q) for q in items], total=len(items), counts=counts)


@router.get("/admin/queue/{item_id}", response_model=QueueDetailOut)
async def get_queue_item(item_id: str, uc: UC, admin: AdminUser):
    return queue_detail_out(uc, uc.get_queue_item(admin, item_id), admin)


@router.post("/admin/queue/{item_id}/decision", response_model=DecisionOut)
async def decide(item_id: str, body: DecisionIn, uc: UC, admin: AdminUser):
    state = uc.decide(admin, item_id, body.action, body.winning_observation_id, body.comment)
    item = uc.get_queue_item(admin, item_id)
    return DecisionOut(id=item.id, status=item.decision, feature_state=feature_state_out(state))


@router.post("/admin/demo/reset", status_code=204)
async def reset_demo(uc: UC, user: OptionalUser):
    uc.reset_demo(user)  # use case enforces admin (401/403)
    return Response(status_code=204)
