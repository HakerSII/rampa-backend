from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DomainError, RateLimited

STATUS_BY_CODE = {
    "VALIDATION_ERROR": 400,
    "NOT_A_REAL_PLACE": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "FILE_TOO_LARGE": 413,
    "RATE_LIMITED": 429,
}
CODE_BY_STATUS = {v: k for k, v in STATUS_BY_CODE.items()}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    body = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"error": body}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimited) else None
        return JSONResponse(error_body(exc.code, exc.message), STATUS_BY_CODE.get(exc.code, 400), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = {"errors": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]}
        return JSONResponse(error_body("VALIDATION_ERROR", "invalid request", details), 400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = CODE_BY_STATUS.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(error_body(code, str(exc.detail)), exc.status_code)
