from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, CurrentUser, Token
from app.adapters.inbound.http.schemas import DemoLoginIn, LoginResult, UserOut, user_out

router = APIRouter(tags=["auth"])


class GoogleLoginIn(BaseModel):
    id_token: str


@router.post("/auth/demo", response_model=LoginResult)
async def login_demo(body: DemoLoginIn, uc: UC):
    token, user = uc.login_demo(body.username)
    return LoginResult(token=token, user=user_out(user))


@router.post("/auth/google", response_model=LoginResult)
async def login_google(body: GoogleLoginIn, uc: UC):
    token, user = await uc.login_with_google(body.id_token)
    return LoginResult(token=token, user=user_out(user))


@router.post("/auth/logout", status_code=204)
async def logout(uc: UC, user: CurrentUser, token: Token):
    uc.logout(token)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user_out(user)
