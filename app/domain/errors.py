class DomainError(Exception):
    code = "DOMAIN_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationFailed(DomainError):
    code = "VALIDATION_ERROR"


class Unauthorized(DomainError):
    code = "UNAUTHORIZED"


class Forbidden(DomainError):
    code = "FORBIDDEN"


class NotFound(DomainError):
    code = "NOT_FOUND"


class ConflictError(DomainError):
    code = "CONFLICT"


class FileTooLarge(DomainError):
    code = "FILE_TOO_LARGE"


class RateLimited(DomainError):
    code = "RATE_LIMITED"

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class NotARealPlace(DomainError):
    code = "NOT_A_REAL_PLACE"
