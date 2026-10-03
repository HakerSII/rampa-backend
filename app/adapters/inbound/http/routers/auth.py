from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, CurrentUser, Token
from app.adapters.inbound.http.schemas import AnonymousLoginIn, DemoLoginIn, LoginResult, UserOut, user_out

router = APIRouter(tags=["auth"])


class GoogleLoginIn(BaseModel):
    id_token: str


@router.post("/auth/anonymous", status_code=201, response_model=LoginResult)
async def login_anonymous(body: AnonymousLoginIn, uc: UC):
    """Device identity for the map front end: a new user per call, long-lived token."""
    token, user = uc.login_anonymous(body.display_name)
    return LoginResult(token=token, user=user_out(user))


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


# ---------------------------------------------------------------- F33 e-mail login
class EmailRequestIn(BaseModel):
    email: str


class EmailRequestOut(BaseModel):
    sent: bool
    dev_token: str | None = None  # AUTH_MODE=demo + MAILER=console only


class EmailVerifyIn(BaseModel):
    token: str


@router.post("/auth/email/request", status_code=202, response_model=EmailRequestOut)
async def email_request(body: EmailRequestIn, uc: UC):
    """Send a one-time login code / link (15 min, single use). Same answer for known and unknown addresses."""
    return EmailRequestOut(sent=True, dev_token=await uc.request_email_login(body.email))


@router.post("/auth/email/verify", response_model=LoginResult)
async def email_verify(body: EmailVerifyIn, uc: UC):
    token, user = uc.verify_email_login(body.token)
    return LoginResult(token=token, user=user_out(user))
