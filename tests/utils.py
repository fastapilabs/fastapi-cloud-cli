import base64
import json
import os
import sys
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Any

from rich.console import detect_legacy_windows
from typer import Typer
from typer.testing import CliRunner, Result


@contextmanager
def changing_dir(directory: str | Path) -> Generator[None, None, None]:
    initial_dir = os.getcwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(initial_dir)


def build_logs_response(*logs: dict[str, Any]) -> str:
    """Helper to create NDJSON build logs response."""
    return "\n".join(json.dumps(log) for log in logs)


class _SnapshotResult(Result):
    @property
    def output(self) -> str:
        output = dedent(super().output.replace("\u200b", "")).strip()
        return "\n".join(line.rstrip() for line in output.splitlines())


class SnapshotCliRunner(CliRunner):
    """Return normalized CLI output suitable for inline snapshots."""

    terminal_width = 80

    def invoke(
        self,
        app: Typer,
        args: str | Sequence[str] | None = None,
        input: bytes | str | None = None,
        env: Mapping[str, str | None] | None = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **extra: Any,
    ) -> _SnapshotResult:
        env = {
            **(env or {}),
            # Rich reserves the final column on legacy Windows terminals.
            "COLUMNS": str(self.terminal_width + int(detect_legacy_windows())),
        }
        result = super().invoke(
            app,
            args,
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **extra,
        )
        return _SnapshotResult(
            runner=result.runner,
            stdout_bytes=result.stdout_bytes,
            stderr_bytes=result.stderr_bytes,
            output_bytes=result.output_bytes,
            return_value=result.return_value,
            exit_code=result.exit_code,
            exception=result.exception,
            exc_info=result.exc_info,
        )


if sys.platform == "win32":

    class Keys:
        RIGHT_ARROW = "\xe0M"
        DOWN_ARROW = "\xe0P"
        ENTER = "\r"
        CTRL_C = "\x03"
        TAB = "\t"
        BACKSPACE = "\x08"

else:

    class Keys:
        RIGHT_ARROW = "\x1b[C"
        DOWN_ARROW = "\x1b[B"
        ENTER = "\r"
        CTRL_C = "\x03"
        TAB = "\t"
        BACKSPACE = "\x7f"


def create_jwt_token(payload: dict[str, Any]) -> str:
    # Note: This creates a JWT with an invalid signature, but that's OK for our tests
    # since we only parse the payload, not verify the signature.

    header = {"alg": "HS256", "typ": "JWT"}
    header_encoded = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )

    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    signature = base64.urlsafe_b64encode(b"signature").decode().rstrip("=")

    return f"{header_encoded}.{payload_encoded}.{signature}"
