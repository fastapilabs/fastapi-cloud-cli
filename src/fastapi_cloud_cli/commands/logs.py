import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from httpx import HTTPError
from pydantic import BaseModel
from rich.markup import escape
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import (
    APIClient,
    AppLogEntry,
    StreamLogError,
    TooManyRetriesError,
    get_http_error_code,
    get_http_error_hint,
    handle_http_error,
)
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.errors import ErrorCode
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


LOG_LEVEL_COLORS = {
    "debug": "blue",
    "info": "cyan",
    "warning": "yellow",
    "warn": "yellow",
    "error": "red",
    "critical": "magenta",
    "fatal": "magenta",
}

SINCE_PATTERN = re.compile(r"^\d+[smhd]$")
MIN_LOG_TAIL = 1
MAX_LOG_TAIL = 1000


class AppLogsOutput(BaseModel):
    app_id: str
    logs: list[AppLogEntry]


def _validate_since(value: str) -> str:
    """Validate the --since parameter format."""
    if not SINCE_PATTERN.match(value):
        raise typer.BadParameter(
            "Invalid format. Use a number followed by s, m, h, or d (e.g., '5m', '1h', '2d')."
        )

    return value


def _validate_tail(value: int) -> int:
    if not MIN_LOG_TAIL <= value <= MAX_LOG_TAIL:
        raise typer.BadParameter(
            f"Invalid value. Use a number between {MIN_LOG_TAIL} and {MAX_LOG_TAIL}."
        )

    return value


def _get_log_bullet(log: AppLogEntry) -> str:
    """Colored indicator rendered in the emoji bullet column.

    ▕ draws at the right edge of its cell, centering the bar under the
    double-width emojis.
    """
    color = LOG_LEVEL_COLORS.get(log.level.lower(), "dim")

    return f"[{color}]▕[/{color}]"


def _format_log_line(log: AppLogEntry) -> str:
    """Format a log entry for display"""
    # Parse the timestamp string to format it consistently
    timestamp = datetime.fromisoformat(log.timestamp.replace("Z", "+00:00"))
    timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    return f"[dim]{timestamp_str}[/dim] {escape(log.message)}"


def _print_log_line(toolkit: RichToolkit, log: AppLogEntry) -> None:
    toolkit.print(_format_log_line(log), emoji=_get_log_bullet(log))


def _render_app_logs_output(data: AppLogsOutput, toolkit: RichToolkit) -> None:
    if not data.logs:
        toolkit.print("No logs found for the specified time range.")
        return

    for log in data.logs:
        _print_log_line(toolkit, log)


def _print_app_log_json(app_id: str, log: AppLogEntry) -> None:
    typer.echo(
        json.dumps(
            {
                "type": "log",
                "app_id": app_id,
                **log.model_dump(mode="json"),
            },
            separators=(",", ":"),
        )
    )


def _render_plain_error(
    toolkit: FastAPIRichToolkit,
    *,
    code: ErrorCode,
    message: str,
    hint: str,
) -> None:
    toolkit.print_error(message)
    if hint:
        toolkit.print_line()
        toolkit.print_hint(hint)


def _handle_stream_log_error(
    toolkit: FastAPIRichToolkit,
    error: StreamLogError,
) -> None:
    hint: str | None = None

    if error.status_code == 404:
        code: ErrorCode = "not_found"
        message = "App not found. Make sure to use the correct account."

    elif isinstance(error.__cause__, HTTPError):
        code = get_http_error_code(error.__cause__)
        message = handle_http_error(error.__cause__)
        hint = get_http_error_hint(code)

        if error.status_code == 400 and hint is None:
            hint = (
                "Try a shorter time range (e.g. `--since 1d`). "
                "Log retention depends on your plan."
            )

    else:
        code = "api_error"
        message = f"[red]Error:[/] {escape(str(error))}"

    toolkit.fail(code, message, hint=hint, render_output=_render_plain_error)


def _process_log_stream(
    toolkit: FastAPIRichToolkit,
    app_id: str,
    tail: int,
    since: str,
    follow: bool,
) -> None:
    """Stream app logs and print them to the console."""
    logs: list[AppLogEntry] = []

    try:
        with APIClient() as client:
            for log in client.stream_app_logs(
                app_id=app_id,
                tail=tail,
                since=since,
                follow=follow,
            ):
                if follow:
                    if toolkit.mode == "json":
                        _print_app_log_json(app_id, log)
                    else:
                        _print_log_line(toolkit, log)
                    continue

                logs.append(log)

            if not follow:
                toolkit.success(
                    AppLogsOutput(app_id=app_id, logs=logs),
                    render_output=_render_app_logs_output,
                )
            return
    except KeyboardInterrupt:  # pragma: no cover
        toolkit.print_line()

        return
    except StreamLogError as e:
        _handle_stream_log_error(toolkit, e)
    except (TooManyRetriesError, TimeoutError):
        message = "Lost connection to log stream. Please try again later."
        toolkit.fail(
            "network_error",
            message,
            hint="Please try again later.",
            render_output=_render_plain_error,
        )


def logs(
    path: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Path to the directory with your app's pyproject.toml "
                "(defaults to current directory)"
            )
        ),
    ] = None,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app whose logs should be fetched.",
        ),
    ] = None,
    tail: int = typer.Option(
        100,
        "--tail",
        "-t",
        help=f"Number of log lines to show before streaming (max {MAX_LOG_TAIL}).",
        show_default=True,
        callback=_validate_tail,
    ),
    since: str = typer.Option(
        "5m",
        "--since",
        "-s",
        help=(
            "Show logs since a specific time (e.g., '5m', '1h', '2d'). "
            "Limited by your plan's log retention."
        ),
        show_default=True,
        callback=_validate_since,
    ),
    follow: bool = typer.Option(
        True,
        "--follow/--no-follow",
        "-f",
        help="Stream logs in real-time (use --no-follow to fetch and exit).",
    ),
    json_output: JsonOutputOption = False,
) -> None:
    """Stream or fetch logs from your deployed app.

    Examples:
        fastapi cloud logs                      # Stream logs in real-time
        fastapi cloud logs --no-follow          # Fetch recent logs and exit
        fastapi cloud logs --tail 50 --since 1h # Last 50 logs from the past hour
    """
    identity = Identity()
    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        target_app_id = resolve_app_id_or_fail(
            toolkit,
            app_id=app_id,
            path=path,
            hint="Pass --app-id or run `fastapi cloud link` to link an app.",
        )

        logger.debug("Fetching logs for app ID: %s", target_app_id)

        if follow:
            toolkit.print(
                f"Streaming logs for [bold]{target_app_id}[/bold] (Ctrl+C to exit)...",
                emoji="📡",
            )
        else:
            toolkit.print(
                f"Fetching logs for [bold]{target_app_id}[/bold]...",
                emoji="📜",
            )
        toolkit.print_line()

        _process_log_stream(
            toolkit=toolkit,
            app_id=target_app_id,
            tail=tail,
            since=since,
            follow=follow,
        )
