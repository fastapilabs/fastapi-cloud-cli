from typing import Literal, NoReturn, Protocol

ErrorCode = Literal[
    "api_error",
    "invalid_token",
    "network_error",
    "not_logged_in",
    "permission_denied",
]


class ErrorToolkit(Protocol):
    def fail(
        self,
        code: ErrorCode,
        message: str,
        *,
        hint: str | None = None,
        exit_code: int = 1,
    ) -> NoReturn: ...
