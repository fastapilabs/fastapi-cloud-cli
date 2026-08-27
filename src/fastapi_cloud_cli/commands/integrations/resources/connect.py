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
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class ResourceConnectOutput(BaseModel):
    app_id: str
    connect_url: str
    app_name: Annotated[str, Field(exclude=True)]
    browser_opened: Annotated[bool, Field(exclude=True)]
    app_id_was_provided: Annotated[bool, Field(exclude=True)]


def _get_resource_connect_url(
    app: App,
    *,
    team_slug: str,
    settings: Settings,
) -> str:
    app_dashboard_url = _get_app_dashboard_url(
        app,
        team_slug=team_slug,
        settings=settings,
    )
    return f"{app_dashboard_url}/integrations/connect"


def _render_resource_connect_output(
    data: ResourceConnectOutput,
    toolkit: RichToolkit,
) -> None:
    toolkit.print_title("connect resource")
    toolkit.print_line()

    if data.browser_opened:
        toolkit.print(
            f"Opened the integration setup for [bold]{data.app_name}[/bold] in your browser.",
            emoji="🔌",
        )
    else:
        toolkit.print(
            f"Open the integration setup for [bold]{data.app_name}[/bold] in your browser:",
            emoji="🔌",
        )

    toolkit.print(Text(data.connect_url, style=f"link {data.connect_url}"))
    toolkit.print_line()

    list_command = "fastapi cloud integrations resources list"
    if data.app_id_was_provided:
        list_command = f"{list_command} --app-id {data.app_id}"

    toolkit.print(
        f"When the connection is complete, run [bold]{list_command}[/bold] to view it.",
        emoji="💡",
    )


def connect_resource(
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app to connect a provider resource to.",
        ),
    ] = None,
    no_open: Annotated[
        bool,
        typer.Option(
            "--no-open",
            help="Do not open the browser automatically.",
        ),
    ] = False,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Open FastAPI Cloud to connect a provider resource to an app.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        app_id_was_provided = app_id is not None
        app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

        with APIClient() as client:
            with (
                toolkit.progress(title="Fetching app", transient=True) as progress,
                client.handle_http_errors(
                    progress,
                    default_message="Error fetching app. Please try again later.",
                    not_found_message="App not found.",
                    toolkit=toolkit,
                ),
            ):
                app = _get_app(client, app_id)

            with (
                toolkit.progress(title="Fetching team", transient=True) as progress,
                client.handle_http_errors(
                    progress,
                    default_message="Error fetching team. Please try again later.",
                    not_found_message="Team not found.",
                    toolkit=toolkit,
                ),
            ):
                team = _get_team(client, app.team_id)

        connect_url = _get_resource_connect_url(
            app,
            team_slug=team.slug,
            settings=Settings.get(),
        )
        browser_opened = False

        if not json_output and not no_open:
            launch_result = typer.launch(connect_url)
            logger.debug("Launch command result: %s", launch_result)
            browser_opened = launch_result == 0

        toolkit.success(
            ResourceConnectOutput(
                app_id=app.id,
                app_name=app.name,
                connect_url=connect_url,
                browser_opened=browser_opened,
                app_id_was_provided=app_id_was_provided,
            ),
            render_output=_render_resource_connect_output,
        )
