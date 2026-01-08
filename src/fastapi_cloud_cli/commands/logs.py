import json
import logging
import time
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from httpx import HTTPError, HTTPStatusError, ReadTimeout
from pydantic import BaseModel, ValidationError
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import AppConfig, get_app_config
from fastapi_cloud_cli.utils.auth import is_logged_in
from fastapi_cloud_cli.utils.cli import get_rich_toolkit

logger = logging.getLogger(__name__)

# Maximum number of reconnection attempts before giving up
MAX_RECONNECT_ATTEMPTS = 10

# Delay between reconnection attempts in seconds
RECONNECT_DELAY_SECONDS = 1

# Colors matching the UI log level indicators
LOG_LEVEL_COLORS = {
    "debug": "blue",
    "info": "cyan",
    "warning": "yellow",
    "warn": "yellow",
    "error": "red",
    "critical": "magenta",
    "fatal": "magenta",
}


class LogEntry(BaseModel):
    timestamp: datetime
    message: str
    level: str = "unknown"


def _stream_logs(
    app_id: str,
    tail: int,
    since: str,
    follow: bool,
) -> Generator[str, None, None]:
    """Stream logs from the API."""
    params: dict[str, Any] = {
        "tail": tail,
        "since": since,
        "follow": follow,
    }

    with APIClient() as client:
        timeout = 120 if follow else 30
        with client.stream(
            "GET",
            f"/apps/{app_id}/logs/stream",
            params=params,
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            yield from response.iter_lines()


def _format_log_line(log: LogEntry) -> str:
    """Format a log entry for display with a colored indicator matching the UI."""
    timestamp_str = log.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    color = LOG_LEVEL_COLORS.get(log.level.lower())
    if color:
        return f"[{color}]┃[/{color}] [dim]{timestamp_str}[/dim] {log.message}"
    return f"[dim]┃[/dim] [dim]{timestamp_str}[/dim] {log.message}"


def _process_log_stream(
    toolkit: RichToolkit,
    app_config: AppConfig,
    tail: int,
    since: str,
    follow: bool,
) -> None:
    """Process the log stream with reconnection logic for follow mode."""
    log_count = 0
    last_timestamp: datetime | None = None
    current_since = since
    current_tail = tail
    reconnect_attempts = 0

    while True:
        try:
            for line in _stream_logs(
                app_id=app_config.app_id,
                tail=current_tail,
                since=current_since,
                follow=follow,
            ):
                if not line:  # pragma: no cover
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Failed to parse log line: %s", line)
                    continue

                # Skip heartbeat messages
                if data.get("type") == "heartbeat":  # pragma: no cover
                    continue

                # Handle error messages from the server
                if data.get("type") == "error":
                    toolkit.print(
                        f"Error: {data.get('message', 'Unknown error')}",
                    )
                    raise typer.Exit(1)

                # Parse and display log entry
                try:
                    log_entry = LogEntry.model_validate(data)
                    toolkit.print(_format_log_line(log_entry))
                    log_count += 1
                    last_timestamp = log_entry.timestamp
                    # Reset reconnect attempts on successful log receipt
                    reconnect_attempts = 0
                except ValidationError as e:  # pragma: no cover
                    logger.debug("Failed to parse log entry: %s - %s", data, e)
                    continue

            # Stream ended normally (only happens with --no-follow)
            if not follow and log_count == 0:
                toolkit.print("No logs found for the specified time range.")
            break

        except KeyboardInterrupt:  # pragma: no cover
            toolkit.print_line()
            break
        except (ReadTimeout, HTTPError) as e:
            # In follow mode, try to reconnect on connection issues
            if follow and not isinstance(e, HTTPStatusError):
                reconnect_attempts += 1
                if reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                    toolkit.print(
                        "Lost connection to log stream. Please try again later.",
                    )
                    raise typer.Exit(1) from None

                logger.debug(
                    "Connection lost, reconnecting (attempt %d/%d)...",
                    reconnect_attempts,
                    MAX_RECONNECT_ATTEMPTS,
                )

                # On reconnect, resume from last seen timestamp
                # The API uses strict > comparison, so logs with the same timestamp
                # as last_timestamp will be filtered out (no duplicates)
                if last_timestamp:
                    current_since = last_timestamp.isoformat()
                    current_tail = 0  # Don't fetch historical logs again

                time.sleep(RECONNECT_DELAY_SECONDS)
                continue

            # Handle non-recoverable errors
            if isinstance(e, HTTPStatusError) and e.response.status_code in (401, 403):
                toolkit.print(
                    "The specified token is not valid. Use [blue]`fastapi login`[/] to generate a new token.",
                )
            elif isinstance(e, ReadTimeout):
                toolkit.print(
                    "The request timed out. Please try again later.",
                )
            else:
                toolkit.print(
                    "Failed to fetch logs. Please try again later.",
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
    ),
    follow: bool = typer.Option(
        True,
        "--follow/--no-follow",
        "-f",
        help="Stream logs in real-time (use --no-follow to fetch and exit).",
    ),
) -> None:
    """Stream or fetch logs from your deployed app."""
    with get_rich_toolkit(minimal=True) as toolkit:
        if not is_logged_in():
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
