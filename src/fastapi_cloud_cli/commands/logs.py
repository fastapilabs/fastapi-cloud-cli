import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.markup import escape
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import (
    APIClient,
    AppLogEntry,
    StreamLogError,
    TooManyRetriesError,
)
from fastapi_cloud_cli.utils.apps import AppConfig, get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit

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


def _process_log_stream(
    toolkit: RichToolkit,
    app_config: AppConfig,
    tail: int,
    since: str,
    follow: bool,
) -> None:
    """Stream app logs and print them to the console."""
    log_count = 0

    try:
        with APIClient() as client:
            for log in client.stream_app_logs(
                app_id=app_config.app_id,
                tail=tail,
                since=since,
                follow=follow,
            ):
                toolkit.print(_format_log_line(log))
                log_count += 1

            if not follow and log_count == 0:
                toolkit.print("No logs found for the specified time range.")
                return
    except KeyboardInterrupt:  # pragma: no cover
        toolkit.print_line()
        return
    except StreamLogError as e:
        error_msg = str(e)
        if "HTTP 401" in error_msg or "HTTP 403" in error_msg:
            toolkit.print(
                "The specified token is not valid. Use [blue]`fastapi login`[/] to generate a new token.",
            )
        elif "HTTP 404" in error_msg:
            toolkit.print(
                "App not found. Make sure to use the correct account.",
            )
        else:
            toolkit.print(
                f"[red]Error:[/] {escape(error_msg)}",
            )
        raise typer.Exit(1) from None
    except (TooManyRetriesError, TimeoutError):
        toolkit.print(
            "Lost connection to log stream. Please try again later.",
        )
        raise typer.Exit(1) from None


def logs(
    path: Annotated[
        Optional[Path],
        typer.Argument(
            help="Path to the folder containing the app (defaults to current directory)"
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
) -> None:
    """Stream or fetch logs from your deployed app.

    Examples:
        fastapi cloud logs                      # Stream logs in real-time
        fastapi cloud logs --no-follow          # Fetch recent logs and exit
        fastapi cloud logs --tail 50 --since 1h # Last 50 logs from the past hour
    """
    identity = Identity()
    with get_rich_toolkit(minimal=True) as toolkit:
        if not identity.is_logged_in():
            toolkit.print(
                "No credentials found. Use [blue]`fastapi login`[/] to login.",
                tag="auth",
            )
            raise typer.Exit(1)

        app_path = path or Path.cwd()
        app_config = get_app_config(app_path)

        if not app_config:
            toolkit.print(
                "No app linked to this directory. Run [blue]`fastapi deploy`[/] first.",
            )
            raise typer.Exit(1)

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
