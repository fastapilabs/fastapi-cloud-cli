import logging
import os
from collections.abc import Callable
from types import TracebackType
from typing import Any, Literal, NoReturn, Protocol, TypeVar

import typer
from pydantic import BaseModel
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from rich_toolkit import RichToolkit, RichToolkitTheme
from rich_toolkit.styles import BaseStyle, MinimalStyle, TaggedStyle

from fastapi_cloud_cli.utils.errors import ErrorCode
from fastapi_cloud_cli.utils.version_check import (
    DISABLE_VERSION_CHECK_ENV,
    BackgroundVersionCheck,
)

logger = logging.getLogger(__name__)

OutputT = TypeVar("OutputT", bound=BaseModel)
OutputRenderer = Callable[[OutputT, RichToolkit], None]


class ErrorRenderer(Protocol):
    def __call__(
        self,
        toolkit: RichToolkit,
        *,
        code: ErrorCode,
        message: str,
        hint: str,
    ) -> None: ...


def _strip_rich_markup(value: str | None) -> str | None:
    if value is None:
        return None

    return Text.from_markup(value).plain


class FastAPIStyle(TaggedStyle):
    def __init__(self, tag_width: int = 11):
        super().__init__(tag_width=tag_width)

    def _get_tag_segments(
        self,
        metadata: dict[str, Any],
        is_animated: bool = False,
        done: bool = False,
        animation_status: Literal["started", "stopped", "error"] | None = None,
    ) -> tuple[list[Segment], int]:
        if not is_animated:
            tag_segments, left_padding = super()._get_tag_segments(
                metadata, is_animated, done, animation_status=animation_status
            )

            tag_style = metadata.get("tag_style")

            if isinstance(tag_style, (str, Style)):
                style = self.console.get_style(tag_style)
                tag_segments = [
                    Segment(segment.text, style=style) for segment in tag_segments
                ]

            return tag_segments, left_padding

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
            tag = metadata.get("done_emoji", emojis[-1])

        if animation_status == "error":
            tag = "🟡"

        left_padding = self.tag_width - 1
        left_padding = max(0, left_padding)

        return [Segment(tag)], left_padding


class FastAPIRichToolkit(RichToolkit):
    mode: Literal["human", "json"]

    def __init__(
        self,
        style: BaseStyle | None = None,
        theme: RichToolkitTheme | None = None,
        mode: Literal["human", "json"] = "human",
    ) -> None:
        super().__init__(style=style, theme=theme, mode=mode)
        self._version_check = self._get_version_check()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        self._print_update_message()

        return super().__exit__(
            exc_type,
            exc_value,
            traceback,
        )

    def _get_version_check(self) -> BackgroundVersionCheck | None:
        if os.environ.get(DISABLE_VERSION_CHECK_ENV) == "1":
            return None

        version_check = BackgroundVersionCheck()
        version_check.start()

        return version_check

    def _print_update_message(self) -> None:
        if self._version_check is None:
            return

        if message := self._version_check.get_update_message():
            self.print_line()
            self.print(Text.from_markup(message), tag="update", tag_style="tag.update")

    def success(
        self,
        data: OutputT,
        *,
        warnings: list[dict[str, Any]] | None = None,
        hint: str | None = None,
        render_output: OutputRenderer[OutputT] | None = None,
    ) -> None:
        if self.mode != "json":
            self.output(data, render_output=render_output)
            return

        output: dict[str, Any] = {"data": data}

        if warnings:
            output["warnings"] = warnings

        if hint is not None:
            output["hint"] = hint

        self.output(output)

    def fail(
        self,
        code: ErrorCode,
        message: str,
        *,
        render_output: ErrorRenderer | None = None,
        hint: str | None = None,
        exit_code: int = 1,
    ) -> NoReturn:
        if self.mode == "json":
            self.output(
                {
                    "error": {
                        "code": code,
                        "message": _strip_rich_markup(message),
                        "hint": _strip_rich_markup(hint),
                    }
                }
            )
        elif render_output is not None:
            render_output(self, code=code, message=message, hint=hint or "")
        else:  # pragma: no cover
            self.print(f"[error]{message}[/]")

            if hint:
                self.print(hint, tag="tip")

        raise typer.Exit(exit_code)


def get_rich_toolkit(
    minimal: bool = False,
    *,
    json_output: bool | None = None,
) -> FastAPIRichToolkit:
    style = MinimalStyle() if minimal else FastAPIStyle(tag_width=11)

    theme = RichToolkitTheme(
        style=style,
        theme={
            "tag.title": "white on #009485",
            "tag": "white on #007166",
            "tag.update": "black on yellow",
            "placeholder": "grey62",
            "text": "white",
            "selected": "#007166",
            "result": "grey85",
            "progress": "on #007166",
            "error": "red",
            "cancelled": "indian_red italic",
        },
    )

    mode: Literal["human", "json"] = "json" if json_output else "human"

    return FastAPIRichToolkit(theme=theme, mode=mode)
