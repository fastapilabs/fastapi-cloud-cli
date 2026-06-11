import logging
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option

from fastapi_cloud_cli.commands.apps.list import _get_app
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import AppConfig, get_app_config, write_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class LinkOutput(BaseModel):
    app_id: str
    team_id: str
    path: Path
    app_name: Annotated[str, Field(exclude=True)]
    config_path: Annotated[Path, Field(exclude=True)]


def _render_link_output(data: LinkOutput, toolkit: RichToolkit) -> None:
    toolkit.print(
        f"Linked [bold]{data.path}[/bold] to [bold]{data.app_name}[/bold]",
        bullet=False,
    )
    toolkit.print(f"Config: [bold]{data.config_path}[/bold]", bullet=False)


def _fail_not_logged_in_interactive(toolkit: FastAPIRichToolkit) -> NoReturn:
    toolkit.fail(
        "not_logged_in",
        "You need to be logged in to link an app.",
        hint="Run [bold]fastapi cloud login[/] to authenticate.",
    )


def _fail_already_linked_interactive(toolkit: FastAPIRichToolkit) -> NoReturn:
    toolkit.fail(
        "already_linked",
        "This directory is already linked to an app.",
        hint="Run [bold]fastapi cloud unlink[/] first to remove the existing configuration.",
    )


def _link_app_by_id(
    toolkit: FastAPIRichToolkit,
    *,
    app_id: str,
    path_to_link: Path,
    force: bool,
) -> None:
    if get_app_config(path_to_link) and not force:
        toolkit.fail(
            "already_linked",
            "This directory is already linked to an app.",
            hint="Pass --force to replace the existing configuration.",
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

    write_app_config(
        path_to_link,
        AppConfig(app_id=app.id, team_id=app.team_id),
    )

    result = LinkOutput(
        app_id=app.id,
        team_id=app.team_id,
        path=path_to_link,
        app_name=app.name,
        config_path=path_to_link / ".fastapicloud" / "cloud.json",
    )

    toolkit.success(result, render_output=_render_link_output)


def _link_app_interactively(
    toolkit: FastAPIRichToolkit,
    *,
    path_to_link: Path,
    force: bool,
) -> None:
    if get_app_config(path_to_link) and not force:
        _fail_already_linked_interactive(toolkit)

    toolkit.print_title("Link to FastAPI Cloud")
    toolkit.print_line()

    with APIClient() as client:
        with toolkit.progress("Fetching teams...", transient=True) as progress:
            with client.handle_http_errors(
                progress,
                default_message="Error fetching teams. Please try again later.",
            ):
                response = client.get("/teams/")
                response.raise_for_status()
                teams_data = response.json()["data"]

        if not teams_data:
            toolkit.print(
                "[error]No teams found. Please create a team first.[/]",
                bullet=False,
            )
            raise typer.Exit(1)

        team = toolkit.ask(
            "Select the team:",
            options=[
                Option({"name": t["name"], "value": {"id": t["id"], "name": t["name"]}})
                for t in sorted(teams_data, key=lambda t: t["name"].lower())
            ],
            allow_filtering=True,
            bullet=False,
        )

        toolkit.print_line()

        with toolkit.progress("Fetching apps...", transient=True) as progress:
            with client.handle_http_errors(
                progress,
                default_message="Error fetching apps. Please try again later.",
            ):
                response = client.get("/apps/", params={"team_id": team["id"]})
                response.raise_for_status()
                apps_data = response.json()["data"]

    if not apps_data:
        toolkit.fail(
            "not_found",
            "No apps found in this team.",
            hint="Run [bold]fastapi cloud apps create[/] to create and deploy a new app.",
        )

    app = toolkit.ask(
        "Select the app to link:",
        options=[
            Option({"name": a["slug"], "value": {"id": a["id"], "slug": a["slug"]}})
            for a in sorted(apps_data, key=lambda a: a["slug"].lower())
        ],
        allow_filtering=True,
        bullet=False,
    )

    toolkit.print_line()

    app_config = AppConfig(app_id=app["id"], team_id=team["id"])
    write_app_config(path_to_link, app_config)

    toolkit.print(
        f"Successfully linked to app [bold]{app['slug']}[/bold]!",
        emoji="🔗",
    )
    logger.debug(f"Linked to app: {app['id']} in team: {team['id']}")


def link_app(
    app_id: Annotated[
        str | None,
        typer.Argument(
            help="ID of the app to link.",
        ),
    ] = None,
    app_id_option: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app to link.",
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Directory to link.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Replace an existing local app configuration.",
        ),
    ] = False,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Link a local directory to an existing FastAPI Cloud app.
    """
    identity = Identity()
    path_to_link = path or Path.cwd()
    target_app_id = app_id_option or app_id

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            if target_app_id is None and not json_output:
                _fail_not_logged_in_interactive(toolkit)

            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        if app_id is not None and app_id_option is not None and app_id != app_id_option:
            toolkit.fail(
                "invalid_input",
                "App ID was provided more than once.",
                hint="Pass either APP_ID or --app-id, not both.",
            )

        if target_app_id is None:
            if json_output:
                toolkit.fail(
                    "missing_required_input",
                    "App ID is required.",
                    hint="Pass an app ID to link an app.",
                )

            _link_app_interactively(
                toolkit,
                path_to_link=path_to_link,
                force=force,
            )
            return

        _link_app_by_id(
            toolkit,
            app_id=target_app_id,
            path_to_link=path_to_link,
            force=force,
        )
