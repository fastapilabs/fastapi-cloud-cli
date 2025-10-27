import logging
import time
from contextlib import AbstractContextManager, contextmanager
from datetime import timedelta
from enum import Enum
from typing import Generator, Optional

import httpx
from pydantic import BaseModel, ValidationError

from fastapi_cloud_cli import __version__
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.auth import get_auth_token

logger = logging.getLogger(__name__)

BUILD_LOG_MAX_RETRIES = 3
BUILD_LOG_TIMEOUT = timedelta(minutes=5)


class BuildLogError(Exception): ...


class BuildLogType(str, Enum):
    message = "message"
    complete = "complete"
    failed = "failed"
    timeout = "timeout"  # Request closed, reconnect to continue
    heartbeat = "heartbeat"  # Keepalive signal when no new logs


class BuildLogLine(BaseModel):
    type: BuildLogType
    message: str | None = None
    id: str | None = None


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
            raise BuildLogError(
                f"HTTP {error.response.status_code}: {error_detail}"
            ) from error


def attempts(
    total_attempts: int = 3, timeout: timedelta = timedelta(minutes=5)
) -> Generator[AbstractContextManager[None], None, None]:
    start = time.monotonic()

    for attempt_number in range(total_attempts):
        if time.monotonic() - start > timeout.total_seconds():
            raise TimeoutError(
                "Build log streaming timed out after %ds", timeout.total_seconds()
            )

        yield attempt(attempt_number)


class APIClient(httpx.Client):
    def __init__(self) -> None:
        settings = Settings.get()

        token = get_auth_token()

        super().__init__(
            base_url=settings.base_api_url,
            timeout=httpx.Timeout(20),
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": f"fastapi-cloud-cli/{__version__}",
            },
        )

    def stream_build_logs(
        self, deployment_id: str
    ) -> Generator[BuildLogLine, None, None]:
        last_id = None

        for attempt in attempts(BUILD_LOG_MAX_RETRIES, BUILD_LOG_TIMEOUT):
            with attempt:
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

                                if log_line.type == BuildLogType.message:
                                    yield log_line

                                if log_line.type in (
                                    BuildLogType.complete,
                                    BuildLogType.failed,
                                ):
                                    yield log_line

                                    return

                                if log_line.type == BuildLogType.timeout:
                                    logger.debug("Received timeout; reconnecting")
                                    break  # Breaks for loop to reconnect

                        else:  # Only triggered if the for loop is not broken
                            logger.debug(
                                "Connection closed by server unexpectedly; attempting to reconnect"
                            )
                            break

                    time.sleep(0.5)

        # Exhausted retries without getting any response
        raise BuildLogError(f"Failed after {BUILD_LOG_MAX_RETRIES} attempts")

    def _parse_log_line(self, line: str) -> Optional[BuildLogLine]:
        try:
            return BuildLogLine.model_validate_json(line)
        except ValidationError as e:
            logger.debug("Skipping malformed log: %s (error: %s)", line[:100], e)
            return None
