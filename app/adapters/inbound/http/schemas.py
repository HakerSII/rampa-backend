"""Pydantic schemas = contract from features/*/openapi.yaml, plus domain → schema mappers."""
from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import Role
from app.domain.model import User


class UserOut(BaseModel):
    id: str
    display_name: str
    email: str | None = None
    role: Role


class LoginResult(BaseModel):
    token: str
    user: UserOut


class DemoLoginIn(BaseModel):
    username: str


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, display_name=user.display_name, email=user.email, role=user.role)


def public_name(display_name: str) -> str:
    """'Anna Kowalska' → 'Anna K.' (privacy rule from mockups)."""
    parts = display_name.split()
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else display_name


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
