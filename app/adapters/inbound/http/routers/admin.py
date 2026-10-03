from fastapi import APIRouter, Response

from app.adapters.inbound.http.deps import UC, AdminUser

router = APIRouter(tags=["admin"])


@router.post("/admin/demo/reset", status_code=204)
async def reset_demo(uc: UC, admin: AdminUser):
    uc.reset_demo(admin)
    return Response(status_code=204)
