from typing import Annotated

from fastapi import Depends, Header, Request

from app.application.use_cases import UseCases
from app.domain.enums import Role
from app.domain.errors import Forbidden, Unauthorized
from app.domain.model import User


def get_use_cases(request: Request) -> UseCases:
    return request.app.state.use_cases


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(uc: Annotated[UseCases, Depends(get_use_cases)],
                 token: Annotated[str | None, Depends(bearer_token)]) -> User | None:
    return uc.current_user(token)


def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise Unauthorized("login required")
    return user


def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if user.role != Role.ADMIN:
        raise Forbidden("admin role required")
    return user


def require_api_key(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> str:
    """Open API auth: X-Api-Key from PUBLIC_API_KEYS, then per-key rate limit."""
    if not x_api_key or x_api_key not in request.app.state.settings.public_api_key_list:
        raise Unauthorized("missing or unknown X-Api-Key")
    request.app.state.rate_limiter.hit(x_api_key)
    return x_api_key


UC = Annotated[UseCases, Depends(get_use_cases)]
OptionalUser = Annotated[User | None, Depends(current_user)]
CurrentUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]
Token = Annotated[str | None, Depends(bearer_token)]
ApiKey = Annotated[str, Depends(require_api_key)]
