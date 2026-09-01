import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
from typing import TypeVar

import httpx
from typing_extensions import ParamSpec

from ._errors import StreamLogError, TooManyRetriesError

logger = logging.getLogger(__name__)

STREAM_LOGS_MAX_RETRIES = 3
STREAM_LOGS_TIMEOUT = timedelta(minutes=5)


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
            # The streaming callers read the body before raising, so the
            # server's error detail is available here.
            raise StreamLogError(
                f"HTTP {error.response.status_code}: {error.response.text}",
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
