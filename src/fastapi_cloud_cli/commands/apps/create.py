import logging
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.apps.list import _prompt_for_team
from fastapi_cloud_cli.commands.deploy.archive import (
    _get_app_name,
    validate_app_directory,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import AppConfig, write_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class CreatedApp(BaseModel):
    id: str
    team_id: str
    slug: str
    name: str
    directory: str | None


class AppsCreateOutput(BaseModel):
    app: CreatedApp
    linked: bool
    path_to_link: Annotated[Path | None, Field(exclude=True)] = None


def _create_app(
    client: APIClient, *, team_id: str, name: str, directory: str | None
) -> CreatedApp:
    response = client.post(
        "/apps/",
        json={"team_id": team_id, "name": name, "directory": directory},
    )
    response.raise_for_status()

    return CreatedApp.model_validate(response.json())


def _render_apps_create_output(data: AppsCreateOutput, toolkit: RichToolkit) -> None:
    toolkit.print(f"Created app [bold]{data.app.name}[/bold]", bullet=False)

    if data.linked and data.path_to_link is not None:
        toolkit.print(
            f"Linked [bold]{data.path_to_link}[/bold] to [bold]{data.app.name}[/bold]",
            bullet=False,
        )


def create_app(
    team_id: Annotated[
        str | None,
        typer.Option(
            "--team-id",
            help="ID of the team where the app should be created.",
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option(
            "--name",
            help="Name of the app to create.",
        ),
    ] = None,
    directory: Annotated[
        str | None,
        typer.Option(
            "--directory",
            help="Directory containing the app's pyproject.toml.",
        ),
    ] = None,
    link: Annotated[
        bool | None,
        typer.Option(
            "--link/--no-link",
            help="Link the local directory to the created app.",
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Directory to link when --link is enabled.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Create a FastAPI Cloud app.
    """
    identity = Identity()
    path_to_link = path or Path.cwd()

    # JSON output is non-interactive, so it defaults to create-only unless --link is explicit.
    link_app = link if link is not None else not json_output

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        if not link_app and path is not None:
            toolkit.fail(
                "invalid_input",
                "Path can only be used when linking.",
                hint="Pass --link or omit --path.",
            )

        with APIClient() as client:
            if team_id is None:
                if json_output:
                    toolkit.fail(
                        "missing_required_input",
                        "Team ID is required.",
                        hint="Pass --team-id to choose a team.",
                    )

                team = _prompt_for_team(toolkit, client)
                team_id = team.id
                toolkit.print_line()

            if name is None:
                if json_output:
                    toolkit.fail(
                        "missing_required_input",
                        "App name is required.",
                        hint="Pass --name to choose an app name.",
                    )

                name = toolkit.input(
                    title="What's your app name?",
                    default=_get_app_name(path_to_link),
                    bullet=False,
                )
                toolkit.print_line()

            directory = validate_app_directory(directory)

            with toolkit.progress(
                title="Creating app",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error creating app. Please try again later.",
                    toolkit=toolkit,
                ):
                    app = _create_app(
                        client,
                        team_id=team_id,
                        name=name,
                        directory=directory,
                    )

        if link_app:
            write_app_config(
                path_to_link,
                AppConfig(app_id=app.id, team_id=app.team_id),
            )

        result = AppsCreateOutput(
            app=app,
            linked=link_app,
            path_to_link=path_to_link if link_app else None,
        )

        toolkit.success(result, render_output=_render_apps_create_output)
