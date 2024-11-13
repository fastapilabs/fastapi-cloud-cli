import contextlib
import logging
from typing import Generator, Optional

import typer
from httpx import HTTPError, HTTPStatusError, ReadTimeout
from rich_toolkit import RichToolkit, RichToolkitTheme
from rich_toolkit.progress import Progress
from rich_toolkit.styles import MinimalStyle, TaggedStyle

logger = logging.getLogger(__name__)


def get_rich_toolkit(minimal: bool = False) -> RichToolkit:
    style = MinimalStyle() if minimal else TaggedStyle(tag_width=11)

    theme = RichToolkitTheme(
        style=style,
        theme={
            "tag.title": "white on #009485",
            "tag": "white on #007166",
            "placeholder": "grey85",
            "text": "white",
            "selected": "#007166",
            "result": "grey85",
            "progress": "on #007166",
            "error": "red",
        },
    )

    return RichToolkit(theme=theme)


@contextlib.contextmanager
def handle_http_errors(
    progress: Progress,
    message: Optional[str] = None,
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

        # Handle validation errors from Pydantic models, this should make it easier to debug :)
        if isinstance(e, HTTPStatusError) and e.response.status_code == 422:
            logger.debug(e.response.json())

        if isinstance(e, HTTPStatusError) and e.response.status_code in (401, 403):
            message = "The specified token is not valid. Use `fastapi login` to generate a new token."

        else:
            message = (
                message
                or f"Something went wrong while contacting the FastAPI Cloud server. Please try again later. \n\n{e}"
            )

        progress.set_error(message)

        raise typer.Exit(1) from None
