import contextlib
import logging
from collections.abc import Generator
from typing import Any

import typer
from httpx import HTTPError, HTTPStatusError, ReadTimeout
from rich.segment import Segment
from rich_toolkit import RichToolkit, RichToolkitTheme
from rich_toolkit.progress import Progress
from rich_toolkit.styles import MinimalStyle, TaggedStyle

from .auth import Identity, delete_auth_config

logger = logging.getLogger(__name__)


class FastAPIStyle(TaggedStyle):
    def __init__(self, tag_width: int = 11):
        super().__init__(tag_width=tag_width)

    def _get_tag_segments(
        self,
        metadata: dict[str, Any],
        is_animated: bool = False,
        done: bool = False,
    ) -> tuple[list[Segment], int]:
        if not is_animated:
            return super()._get_tag_segments(metadata, is_animated, done)

        emojis = [
            "🥚",
            "🐣",
            "🐤",
            "🐥",
            "🐓",
            "🐔",
        ]

        tag = emojis[self.animation_counter % len(emojis)]

        if done:
            tag = emojis[-1]

        left_padding = self.tag_width - 1
        left_padding = max(0, left_padding)

        return [Segment(tag)], left_padding


def get_rich_toolkit(minimal: bool = False) -> RichToolkit:
    style = MinimalStyle() if minimal else FastAPIStyle(tag_width=11)

    theme = RichToolkitTheme(
        style=style,
        theme={
            "tag.title": "white on #009485",
            "tag": "white on #007166",
            "placeholder": "grey62",
            "text": "white",
            "selected": "#007166",
            "result": "grey85",
            "progress": "on #007166",
            "error": "red",
            "cancelled": "indian_red italic",
        },
    )

    return RichToolkit(theme=theme)


def handle_unauthorized() -> str:
    message = "The specified token is not valid. "

    identity = Identity()

    if identity.auth_mode == "user":
        delete_auth_config()

        message += "Use `fastapi login` to generate a new token."
    else:
        message += "Make sure to use a valid token."

    return message


def handle_http_error(error: HTTPError, default_message: str | None = None) -> str:
    message: str | None = None

    if isinstance(error, HTTPStatusError):
        status_code = error.response.status_code

        # Handle validation errors from Pydantic models, this should make it easier to debug :)
        if status_code == 422:
            logger.debug(error.response.json())  # pragma: no cover

        elif status_code == 401:
            message = handle_unauthorized()

        elif status_code == 403:
            message = "You don't have permissions for this resource"

    if not message:
        message = (
            default_message
            or f"Something went wrong while contacting the FastAPI Cloud server. Please try again later. \n\n{error}"
        )

    return message


@contextlib.contextmanager
def handle_http_errors(
    progress: Progress,
    default_message: str | None = None,
) -> Generator[None, None, None]:
    try:
        yield
    except ReadTimeout as e:
        logger.debug(e)

        progress.set_error(
            "The request to the FastAPI Cloud server timed out. Please try again later."
        )

        raise typer.Exit(1) from None
    except HTTPError as e:
        logger.debug(e)

        message = handle_http_error(e, default_message)

        progress.set_error(message)

        raise typer.Exit(1) from None
