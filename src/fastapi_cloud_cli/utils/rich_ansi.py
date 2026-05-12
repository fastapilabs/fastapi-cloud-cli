import re

from rich.ansi import AnsiDecoder
from rich.text import Text

ANSI_NEWLINE_SPLIT_RE = re.compile(r"(?<=\n)")


def text_from_ansi(text: str) -> Text:
    # Text.from_ansi only preserves newlines in Rich 15, in order to
    # avoid forcing everyone to use Rich 15 we handle this ourselves by splitting the text on newlines,
    # decoding each line separately, then join them back together with newlines.
    joiner = Text("\n")
    decoder = AnsiDecoder()

    return joiner.join(
        decoder.decode_line(line.rstrip("\n"))
        for line in ANSI_NEWLINE_SPLIT_RE.split(text)
    )
