from typing import Literal, NoReturn, Protocol

ErrorCode = Literal[
    "api_error",
    "invalid_token",
    "network_error",
    "not_found",
    "not_logged_in",
    "permission_denied",
]


class ErrorToolkit(Protocol):
    mode: Literal["json", "human"]

    def fail(
        self,
        code: ErrorCode,
        message: str,
        *,
        hint: str | None = None,
        exit_code: int = 1,
    ) -> NoReturn: ...
