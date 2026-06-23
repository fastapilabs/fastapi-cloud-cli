from typing import Literal, NoReturn, Protocol

ErrorCode = Literal[
    "already_linked",
    "api_error",
    "cancelled",
    "dependency_missing",
    "invalid_token",
    "invalid_input",
    "missing_required_input",
    "network_error",
    "not_found",
    "not_linked",
    "not_logged_in",
    "permission_denied",
    "timeout",
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
