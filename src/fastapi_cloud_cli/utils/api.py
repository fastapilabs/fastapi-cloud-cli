import json
import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import timedelta
from enum import Enum
from functools import wraps
from typing import (
    Annotated,
    Literal,
    TypeVar,
)

import httpx
import typer
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from rich_toolkit.progress import Progress
from typing_extensions import ParamSpec

from fastapi_cloud_cli import __version__
from fastapi_cloud_cli.config import Settings

from .auth import AuthMode, Identity, delete_auth_config

logger = logging.getLogger(__name__)

STREAM_LOGS_MAX_RETRIES = 3
STREAM_LOGS_TIMEOUT = timedelta(minutes=5)


class StreamLogError(Exception):
    """Raised when there's an error streaming logs (build or app logs)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TooManyRetriesError(Exception):
    pass


class AppLogEntry(BaseModel):
    timestamp: str
    message: str
    level: str


class BuildLogLineGeneric(BaseModel):
    type: Literal["complete", "failed", "timeout", "heartbeat"]
    id: str | None = None


class BuildLogLineMessage(BaseModel):
    type: Literal["message"] = "message"
    message: str
    id: str | None = None


BuildLogLine = BuildLogLineMessage | BuildLogLineGeneric
BuildLogAdapter: TypeAdapter[BuildLogLine] = TypeAdapter(
    Annotated[BuildLogLine, Field(discriminator="type")]
)


@contextmanager
def attempt(attempt_number: int) -> Generator[None, None, None]:
    def _backoff() -> None:
        backoff_seconds = min(2**attempt_number, 30)
        logger.debug(
            "Retrying in %ds (attempt %d)",
            backoff_seconds,
            attempt_number,
        )
        time.sleep(backoff_seconds)

    try:
        yield

    except (
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    ) as error:
        logger.debug("Network error (will retry): %s", error)

        _backoff()

    except httpx.HTTPStatusError as error:
        if error.response.status_code >= 500:
            logger.debug(
                "Server error %d (will retry): %s",
                error.response.status_code,
                error,
            )
            _backoff()
        else:
            # Try to get response text, but handle streaming responses gracefully
            try:
                error_detail = error.response.text
            except Exception:
                error_detail = "(response body unavailable)"
            raise StreamLogError(
                f"HTTP {error.response.status_code}: {error_detail}",
                status_code=error.response.status_code,
            ) from error


P = ParamSpec("P")
T = TypeVar("T")


def attempts(
    total_attempts: int = 3, timeout: timedelta = timedelta(minutes=5)
) -> Callable[
    [Callable[P, Generator[T, None, None]]], Callable[P, Generator[T, None, None]]
]:
    def decorator(
        func: Callable[P, Generator[T, None, None]],
    ) -> Callable[P, Generator[T, None, None]]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Generator[T, None, None]:
            start = time.monotonic()

            for attempt_number in range(total_attempts):
                if time.monotonic() - start > timeout.total_seconds():
                    raise TimeoutError(
                        f"Log streaming timed out after {timeout.total_seconds():.0f}s"
                    )

                with attempt(attempt_number):
                    yield from func(*args, **kwargs)
                    # If we get here without exception, the generator completed successfully
                    return

            raise TooManyRetriesError(f"Failed after {total_attempts} attempts")

        return wrapper

    return decorator


class DeploymentStatus(str, Enum):
    waiting_upload = "waiting_upload"
    upload_cancelled = "upload_cancelled"
    ready_for_build = "ready_for_build"
    building = "building"
    extracting = "extracting"
    extracting_failed = "extracting_failed"
    building_image = "building_image"
    building_image_failed = "building_image_failed"
    deploying = "deploying"
    deploying_failed = "deploying_failed"
    verifying = "verifying"
    verifying_failed = "verifying_failed"
    verifying_skipped = "verifying_skipped"
    success = "success"
    expired = "expired"
    failed = "failed"

    @classmethod
    def to_human_readable(cls, status: "DeploymentStatus") -> str:
        return {
            cls.waiting_upload: "Awaiting Upload",
            cls.upload_cancelled: "Upload Cancelled",
            cls.ready_for_build: "Build Queued",
            cls.building: "Building",
            cls.extracting: "Extracting Upload",
            cls.extracting_failed: "Extraction Failed",
            cls.building_image: "Building Image",
            cls.building_image_failed: "Build Failed",
            cls.deploying: "Deploying Image",
            cls.deploying_failed: "Deployment Failed",
            cls.verifying: "Verifying Readiness",
            cls.verifying_failed: "Verification Failed",
            cls.verifying_skipped: "Verification Skipped",
            cls.success: "Ready",
            cls.expired: "Expired",
            cls.failed: "Failed",
        }[status]


SUCCESSFUL_STATUSES = {DeploymentStatus.success, DeploymentStatus.verifying_skipped}
FAILED_STATUSES = {
    DeploymentStatus.failed,
    DeploymentStatus.verifying_failed,
    DeploymentStatus.deploying_failed,
    DeploymentStatus.building_image_failed,
    DeploymentStatus.extracting_failed,
}
TERMINAL_STATUSES = SUCCESSFUL_STATUSES | FAILED_STATUSES

POLL_INTERVAL = 2.0
POLL_TIMEOUT = timedelta(seconds=120)
POLL_MAX_RETRIES = 5


def _handle_unauthorized(auth_mode: AuthMode) -> str:
    message = "The specified token is not valid. "

    if auth_mode == "user":
        delete_auth_config()

        message += "Use `fastapi login` to generate a new token."
    else:
        message += "Make sure to use a valid token."

    return message


def handle_http_error(
    error: httpx.HTTPError,
    default_message: str | None = None,
    auth_mode: AuthMode = "user",
) -> str:
    message: str | None = None

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code

        # Handle validation errors from Pydantic models, this should make it easier to debug :)
        if status_code == 422:
            logger.debug(error.response.json())  # pragma: no cover

        elif status_code == 401:
            message = _handle_unauthorized(auth_mode=auth_mode)

        elif status_code == 403:
            message = "You don't have permissions for this resource"

    if not message:
        message = (
            default_message
            or f"Something went wrong while contacting the FastAPI Cloud server. Please try again later. \n\n{error}"
        )

    return message


class APIClient(httpx.Client):
    auth_mode: AuthMode

    def __init__(self, use_deploy_token: bool = False) -> None:
        settings = Settings.get()
        identity = Identity()

        token: str | None
        if use_deploy_token and identity.deploy_token:
            token = identity.deploy_token
            self.auth_mode = "token"
        else:
            token = identity.user_token
            self.auth_mode = "user"

        headers = {"User-Agent": f"fastapi-cloud-cli/{__version__}"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        super().__init__(
            base_url=settings.base_api_url,
            timeout=httpx.Timeout(20),
            headers=headers,
        )

    @contextmanager
    def handle_http_errors(
        self,
        progress: Progress,
        default_message: str | None = None,
    ) -> Generator[None, None, None]:
        try:
            yield
        except httpx.ReadTimeout as e:
            logger.debug(e)

            progress.set_error(
                "The request to the FastAPI Cloud server timed out."
                " Please try again later."
            )

            raise typer.Exit(1) from None
        except httpx.HTTPError as e:
            logger.debug(e)

            message = handle_http_error(e, default_message, auth_mode=self.auth_mode)

            progress.set_error(message)

            raise typer.Exit(1) from None

    @attempts(STREAM_LOGS_MAX_RETRIES, STREAM_LOGS_TIMEOUT)
    def stream_build_logs(
        self, deployment_id: str
    ) -> Generator[BuildLogLine, None, None]:
        last_id = None

        while True:
            params = {"last_id": last_id} if last_id else None

            with self.stream(
                "GET",
                f"/deployments/{deployment_id}/build-logs",
                timeout=60,
                params=params,
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line or not line.strip():
                        continue

                    if log_line := self._parse_log_line(line):
                        if log_line.id:
                            last_id = log_line.id

                        if log_line.type == "message":
                            yield log_line

                        if log_line.type in ("complete", "failed"):
                            yield log_line
                            return

                        if log_line.type == "timeout":
                            logger.debug("Received timeout; reconnecting")
                            break  # Breaks for loop to reconnect
                else:
                    logger.debug("Connection closed by server unexpectedly; will retry")

                    raise httpx.NetworkError("Connection closed without terminal state")

            time.sleep(0.5)

    def _parse_log_line(self, line: str) -> BuildLogLine | None:
        try:
            return BuildLogAdapter.validate_json(line)
        except (ValidationError, json.JSONDecodeError) as e:
            logger.debug("Skipping malformed log: %s (error: %s)", line[:100], e)
            return None

    @attempts(STREAM_LOGS_MAX_RETRIES, STREAM_LOGS_TIMEOUT)
    def stream_app_logs(
        self,
        app_id: str,
        tail: int,
        since: str,
        follow: bool,
    ) -> Generator[AppLogEntry, None, None]:
        timeout = 120 if follow else 30
        with self.stream(
            "GET",
            f"/apps/{app_id}/logs/stream",
            params={
                "tail": tail,
                "since": since,
                "follow": follow,
            },
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.strip():  # pragma: no cover
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Failed to parse log line: %s", line)
                    continue

                if data.get("type") == "heartbeat":
                    continue

                if data.get("type") == "error":
                    raise StreamLogError(data.get("message", "Unknown error"))

                try:
                    yield AppLogEntry.model_validate(data)
                except ValidationError as e:  # pragma: no cover
                    logger.debug("Failed to parse log entry: %s - %s", data, e)
                    continue

    def poll_deployment_status(
        self,
        app_id: str,
        deployment_id: str,
    ) -> DeploymentStatus:
        start = time.monotonic()
        error_count = 0

        while True:
            if time.monotonic() - start > POLL_TIMEOUT.total_seconds():
                raise TimeoutError("Deployment verification timed out")

            with attempt(error_count):
                response = self.get(f"/apps/{app_id}/deployments/{deployment_id}")
                response.raise_for_status()
                status = DeploymentStatus(response.json()["status"])
                error_count = 0

                if status in TERMINAL_STATUSES:
                    return status

                time.sleep(POLL_INTERVAL)
                continue

            error_count += 1
            if error_count >= POLL_MAX_RETRIES:
                raise TooManyRetriesError(
                    f"Failed after {POLL_MAX_RETRIES} attempts polling deployment status"
                )
