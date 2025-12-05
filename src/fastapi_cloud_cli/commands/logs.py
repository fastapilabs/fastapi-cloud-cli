import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Union

import typer
from pydantic import BaseModel
from typing_extensions import Annotated

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import is_logged_in
from fastapi_cloud_cli.utils.cli import get_rich_toolkit, handle_http_errors

logger = logging.getLogger(__name__)


class LogEntry(BaseModel):
    timestamp: datetime
    message: str
    level: str = "unknown"


def _stream_logs(
    app_id: str,
    tail: int,
    since: str,
    no_follow: bool,
) -> Generator[str, None, None]:
    """Stream logs from the API."""
    params = {
        "tail": tail,
        "since": since,
        "no_follow": no_follow,
    }

    with APIClient() as client:
        timeout = 30 if no_follow else 120
        with client.stream(
            "GET",
            f"/apps/{app_id}/logs/stream",
            params=params,
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            yield from response.iter_lines()


def _format_log_line(log: LogEntry) -> str:
    """Format a log entry for display."""
    timestamp_str = log.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    level_upper = log.level.upper()
    return f"{timestamp_str} [{level_upper}] {log.message}"


def logs(
    path: Annotated[
        Union[Path, None],
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
    no_follow: bool = typer.Option(
        False,
        "--no-follow",
        "-n",
        help="Fetch recent logs and exit (don't stream).",
    ),
) -> Any:
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

        logger.debug(f"Fetching logs for app ID: {app_config.app_id}")

        if no_follow:
            toolkit.print("Fetching logs...", tag="logs")
        else:
            toolkit.print("Streaming logs (Ctrl+C to exit)...", tag="logs")
        toolkit.print_line()

        try:
            log_count = 0
            with handle_http_errors(
                progress=None,
                message="Failed to fetch logs. Please try again later.",
            ):
                for line in _stream_logs(
                    app_id=app_config.app_id,
                    tail=tail,
                    since=since,
                    no_follow=no_follow,
                ):
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Failed to parse log line: %s", line)
                        continue

                    # Skip heartbeat messages
                    if data.get("type") == "heartbeat":
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
                    except Exception as e:
                        logger.debug("Failed to parse log entry: %s - %s", data, e)
                        continue

            if no_follow and log_count == 0:
                toolkit.print("No logs found for the specified time range.")

        except KeyboardInterrupt:
            toolkit.print_line()
            toolkit.print("Stopped.", tag="logs")
