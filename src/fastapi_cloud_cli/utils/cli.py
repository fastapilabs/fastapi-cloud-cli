import logging
from typing import Any, Literal

from rich.segment import Segment
from rich_toolkit import RichToolkit, RichToolkitTheme
from rich_toolkit.styles import MinimalStyle, TaggedStyle

logger = logging.getLogger(__name__)


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
            return super()._get_tag_segments(
                metadata, is_animated, done, animation_status=animation_status
            )

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
