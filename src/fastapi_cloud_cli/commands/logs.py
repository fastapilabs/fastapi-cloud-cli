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
from fastapi_cloud_cli.utils.apps import AppConfig, get_app_config
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


def _format_log_line(log: AppLogEntry) -> str:
    """Format a log entry for display with a colored indicator"""
    # Parse the timestamp string to format it consistently
    timestamp = datetime.fromisoformat(log.timestamp.replace("Z", "+00:00"))
    timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    color = LOG_LEVEL_COLORS.get(log.level.lower())

    message = escape(log.message)

    if color:
        return f"[{color}]┃[/{color}] [dim]{timestamp_str}[/dim] {message}"

    return f"[dim]┃[/dim] [dim]{timestamp_str}[/dim] {message}"


def _render_app_logs_output(data: AppLogsOutput, toolkit: RichToolkit) -> None:
    if not data.logs:
        toolkit.print("No logs found for the specified time range.")
        return

    for log in data.logs:
        toolkit.print(_format_log_line(log))


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


def _render_not_logged_in_error(
    toolkit: RichToolkit,
    *,
    code: ErrorCode,
    message: str,
    hint: str,
) -> None:
    toolkit.print(message, tag="auth")
    if hint:
        toolkit.print_line()
        toolkit.print(hint, tag="tip")


def _render_app_not_configured_error(
    toolkit: RichToolkit,
    *,
    code: ErrorCode,
    message: str,
    hint: str,
) -> None:
    toolkit.print(message)
    if hint:
        toolkit.print_line()
        toolkit.print(hint, tag="tip")


def _render_plain_error(
    toolkit: RichToolkit,
    *,
    code: ErrorCode,
    message: str,
    hint: str,
) -> None:
    toolkit.print(message)
    if hint:
        toolkit.print_line()
        toolkit.print(hint, tag="tip")


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

    else:
        code = "api_error"
        message = f"[red]Error:[/] {escape(str(error))}"

    toolkit.fail(code, message, hint=hint, render_output=_render_plain_error)


def _process_log_stream(
    toolkit: FastAPIRichToolkit,
    app_config: AppConfig,
    tail: int,
    since: str,
    follow: bool,
) -> None:
    """Stream app logs and print them to the console."""
    logs: list[AppLogEntry] = []

    try:
        with APIClient() as client:
            for log in client.stream_app_logs(
                app_id=app_config.app_id,
                tail=tail,
                since=since,
                follow=follow,
            ):
                if follow:
                    if toolkit.mode == "json":
                        _print_app_log_json(app_config.app_id, log)
                    else:
                        toolkit.print(_format_log_line(log))
                    continue

                logs.append(log)

            if not follow:
                toolkit.success(
                    AppLogsOutput(app_id=app_config.app_id, logs=logs),
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
    tail: int = typer.Option(
        100,
        "--tail",
        "-t",
        help="Number of log lines to show before streaming.",
        show_default=True,
    ),
    since: str = typer.Option(
        "5m",
        "--since",
        "-s",
        help="Show logs since a specific time (e.g., '5m', '1h', '2d').",
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
    with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
                render_output=_render_not_logged_in_error,
            )

        app_path = path or Path.cwd()
        app_config = get_app_config(app_path)

        if not app_config:
            toolkit.fail(
                "missing_required_input",
                "No app linked to this directory.",
                hint="Run `fastapi cloud apps create --link` first.",
                render_output=_render_app_not_configured_error,
            )
        assert app_config is not None

        logger.debug("Fetching logs for app ID: %s", app_config.app_id)

        if follow:
            toolkit.print(
                f"Streaming logs for [bold]{app_config.app_id}[/bold] (Ctrl+C to exit)...",
                tag="logs",
            )
        else:
            toolkit.print(
                f"Fetching logs for [bold]{app_config.app_id}[/bold]...",
                tag="logs",
            )
        toolkit.print_line()

        _process_log_stream(
            toolkit=toolkit,
            app_config=app_config,
            tail=tail,
            since=since,
            follow=follow,
        )
