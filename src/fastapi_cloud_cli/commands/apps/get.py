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
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class AppGetOutput(BaseModel):
    app: App
    dashboard_url: Annotated[str | None, Field(exclude=True)] = None


def _render_app_get_output(data: AppGetOutput, toolkit: RichToolkit) -> None:
    app = data.app

    toolkit.print(f"[bold]{app.name}[/bold]", tag="app")
    toolkit.print_line()
    toolkit.print(app.id, tag="id", tag_style="text")
    toolkit.print(app.slug, tag="slug", tag_style="text")
    toolkit.print(
        app.directory if app.directory is not None else Text("-", style="dim"),
        tag="directory",
        tag_style="text",
    )
    toolkit.print(
        app.url if app.url is not None else Text("-", style="dim"),
        tag="url",
        tag_style="text",
    )
    toolkit.print(
        (
            Text(data.dashboard_url, style=f"link {data.dashboard_url}")
            if data.dashboard_url is not None
            else Text("-", style="dim")
        ),
        tag="dashboard",
        tag_style="text",
    )
    toolkit.print(app.team_id, tag="team id", tag_style="text")


def get_app(
    app_id: Annotated[
        str,
        typer.Argument(
            help="ID of the app to return.",
        ),
    ],
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
                    app = _get_app(client, app_id)

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
