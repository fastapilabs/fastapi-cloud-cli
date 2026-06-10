import logging
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.apps.list import (
    App,
    _get_app,
    _get_app_dashboard_url,
    _get_team,
)
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_details_table, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class AppGetOutput(BaseModel):
    app: App
    dashboard_url: Annotated[str | None, Field(exclude=True)] = None


def _render_app_get_output(data: AppGetOutput, toolkit: RichToolkit) -> None:
    app = data.app

    toolkit.print(f"[bold]{app.name}[/bold]", emoji="📦")
    toolkit.print_line()
    toolkit.print(
        get_details_table(
            [
                ("id", app.id),
                ("slug", app.slug),
                (
                    "directory",
                    app.directory
                    if app.directory is not None
                    else Text("-", style="dim"),
                ),
                ("url", app.url if app.url is not None else Text("-", style="dim")),
                (
                    "dashboard",
                    Text(data.dashboard_url, style=f"link {data.dashboard_url}")
                    if data.dashboard_url is not None
                    else Text("-", style="dim"),
                ),
                ("team id", app.team_id),
            ]
        )
    )


def get_app(
    app_id: Annotated[
        str | None,
        typer.Argument(
            help="ID of the app to return (defaults to the app linked to the current directory).",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Get a FastAPI Cloud app by ID.
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
            hint="Pass an app ID or run `fastapi cloud apps create --link` first.",
        )

        with APIClient() as client:
            with toolkit.progress(
                title="Fetching app",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error fetching app. Please try again later.",
                    not_found_message="App not found.",
                    toolkit=toolkit,
                ):
                    app = _get_app(client, target_app_id)

            dashboard_url = None
            if not json_output:
                with toolkit.progress(
                    title="Fetching team",
                    transient=True,
                ) as progress:
                    with client.handle_http_errors(
                        progress,
                        default_message="Error fetching team. Please try again later.",
                        not_found_message="Team not found.",
                        toolkit=toolkit,
                    ):
                        team = _get_team(client, app.team_id)

                dashboard_url = _get_app_dashboard_url(
                    app,
                    team_slug=team.slug,
                    settings=Settings.get(),
                )

            result = AppGetOutput(app=app, dashboard_url=dashboard_url)

        toolkit.success(result, render_output=_render_app_get_output)
