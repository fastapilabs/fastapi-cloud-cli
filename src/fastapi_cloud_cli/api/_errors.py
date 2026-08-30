import json
import logging

import httpx

from fastapi_cloud_cli.utils.auth import AuthMode, delete_auth_config
from fastapi_cloud_cli.utils.errors import ErrorCode

logger = logging.getLogger(__name__)


class StreamLogError(Exception):
    """Raised when there's an error streaming logs (build or app logs)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TooManyRetriesError(Exception):
    pass


def _handle_unauthorized(auth_mode: AuthMode) -> str:
    message = "The specified token is not valid. "

    if auth_mode == "user":
        delete_auth_config()

        message += "Use `fastapi login` to generate a new token."
    else:
        message += "Make sure to use a valid token."

    return message


def _get_response_error_message(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except (json.JSONDecodeError, httpx.ResponseNotRead):
        return None

    if not isinstance(data, dict):
        return None  # pragma: no cover

    detail = data.get("detail")
    if isinstance(detail, str):
        return detail

    if (
        isinstance(detail, list)
        and detail
        and isinstance(detail[0], dict)
        and isinstance(message := detail[0].get("msg"), str)
    ):
        return message.removeprefix("Value error, ")

    return None  # pragma: no cover


def handle_http_error(
    error: httpx.HTTPError,
    default_message: str | None = None,
    not_found_message: str | None = None,
    auth_mode: AuthMode = "user",
) -> str:
    message: str | None = None

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code

        if status_code == 422:
            logger.debug(error.response.json())
            message = _get_response_error_message(error.response)

        elif status_code == 400:
            message = _get_response_error_message(error.response)

        elif status_code == 409:
            message = _get_response_error_message(error.response)

        elif status_code == 401:
            message = _handle_unauthorized(auth_mode=auth_mode)

        elif status_code == 403:
            message = (
                _get_response_error_message(error.response)
                or "You don't have permissions for this resource"
            )

        elif status_code == 404:
            message = (
                _get_response_error_message(error.response)
                or not_found_message
                or "Resource not found."
            )

    if not message:
        message = (
            default_message
            or f"Something went wrong while contacting the FastAPI Cloud server. Please try again later. \n\n{error}"
        )

    return message


def get_http_error_code(error: httpx.HTTPError) -> ErrorCode:
    if isinstance(error, httpx.TimeoutException | httpx.NetworkError):
        return "network_error"

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code

        if status_code in {400, 409, 422}:
            return "invalid_input"

        if status_code == 401:
            return "invalid_token"

        if status_code == 403:
            return "permission_denied"

        if status_code == 404:
            return "not_found"

    return "api_error"


def get_http_error_hint(code: ErrorCode, *, auth_mode: AuthMode = "user") -> str | None:
    if code == "invalid_token":
        if auth_mode == "user":
            return "Run `fastapi cloud login` to generate a new token."

        return "Make sure FASTAPI_CLOUD_TOKEN contains a valid token."

    return None
