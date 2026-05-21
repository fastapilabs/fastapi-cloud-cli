import logging
import os
from types import TracebackType
from typing import Any, Literal

import click
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from rich_toolkit import RichToolkit, RichToolkitTheme
from rich_toolkit.styles import BaseStyle, MinimalStyle, TaggedStyle

from fastapi_cloud_cli.utils.version_check import (
    DISABLE_VERSION_CHECK_ENV,
    BackgroundVersionCheck,
)

logger = logging.getLogger(__name__)
VERSION_CHECK_CONTEXT_KEY = "fastapi_cloud_cli.version_check"


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
    def __init__(
        self,
        style: BaseStyle | None = None,
        theme: RichToolkitTheme | None = None,
        handle_keyboard_interrupts: bool = True,
        print_spacing: bool = True,
    ) -> None:
        super().__init__(
            style=style,
            theme=theme,
            handle_keyboard_interrupts=handle_keyboard_interrupts,
        )
        self._print_spacing = print_spacing
        self._version_check: BackgroundVersionCheck | None = None
        self._print_update_on_exit = False

    def __enter__(self) -> "FastAPIRichToolkit":
        self._version_check = self._get_version_check()

        if self._print_spacing:
            self.console.print()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        is_keyboard_interrupt = exc_type is KeyboardInterrupt

        if is_keyboard_interrupt and self._version_check is not None:
            self._version_check.suppress()
        elif self._print_update_on_exit:
            self._print_update_message()

        if self._print_spacing and not is_keyboard_interrupt:
            self.console.print()

        if self.handle_keyboard_interrupts and is_keyboard_interrupt:
            return True

        return None

    def _get_version_check(self) -> BackgroundVersionCheck | None:
        if os.environ.get(DISABLE_VERSION_CHECK_ENV) == "1":
            return None

        context = click.get_current_context(silent=True)
        if context is None:
            version_check = BackgroundVersionCheck()
            version_check.start()
            self._print_update_on_exit = True
            return version_check

        stored_version_check = context.meta.get(VERSION_CHECK_CONTEXT_KEY)
        if isinstance(stored_version_check, BackgroundVersionCheck):
            return stored_version_check

        version_check = BackgroundVersionCheck()
        version_check.start()
        context.meta[VERSION_CHECK_CONTEXT_KEY] = version_check
        context.call_on_close(self._print_update_message)

        return version_check

    def _print_update_message(self) -> None:
        if self._version_check is None:
            return

        message = self._version_check.get_update_message()
        if message:
            self.print(Text.from_markup(message), tag="update", tag_style="tag.update")


def get_rich_toolkit(
    minimal: bool = False,
    *,
    print_spacing: bool = True,
    handle_keyboard_interrupts: bool = True,
) -> RichToolkit:
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

    return FastAPIRichToolkit(
        theme=theme,
        handle_keyboard_interrupts=handle_keyboard_interrupts,
        print_spacing=print_spacing,
    )
