import json
import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
from typing import (
    Annotated,
    Literal,
    TypeVar,
)

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from typing_extensions import ParamSpec

from fastapi_cloud_cli import __version__
from fastapi_cloud_cli.config import Settings

from .auth import Identity

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


class APIClient(httpx.Client):
    def __init__(self) -> None:
        settings = Settings.get()
        identity = Identity()

        super().__init__(
            base_url=settings.base_api_url,
            timeout=httpx.Timeout(20),
            headers={
                "Authorization": f"Bearer {identity.token}",
                "User-Agent": f"fastapi-cloud-cli/{__version__}",
            },
        )

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
