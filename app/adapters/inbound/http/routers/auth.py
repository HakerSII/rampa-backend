from fastapi import APIRouter

from app.adapters.inbound.http.deps import UC
from app.adapters.inbound.http.schemas import DemoLoginIn, LoginResult, user_out

router = APIRouter(tags=["auth"])


@router.post("/auth/demo", response_model=LoginResult)
async def login_demo(body: DemoLoginIn, uc: UC):
    token, user = uc.login_demo(body.username)
    return LoginResult(token=token, user=user_out(user))
