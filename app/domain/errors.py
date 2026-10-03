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
