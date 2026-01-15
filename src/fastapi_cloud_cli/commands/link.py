import logging
from pathlib import Path
from typing import Any

import typer
from rich_toolkit.menu import Option

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import AppConfig, get_app_config, write_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit, handle_http_errors

logger = logging.getLogger(__name__)


def link() -> Any:
    """
    Link a local directory to an existing FastAPI Cloud app.
    """
    identity = Identity()

    with get_rich_toolkit() as toolkit:
        if not identity.is_logged_in():
            toolkit.print(
                "[error]You need to be logged in to link an app.[/]",
            )
            toolkit.print_line()
            toolkit.print(
                "Run [bold]fastapi cloud login[/] to authenticate.",
                tag="tip",
            )
            raise typer.Exit(1)

        path_to_link = Path.cwd()

        if get_app_config(path_to_link):
            toolkit.print(
                "[error]This directory is already linked to an app.[/]",
            )
            toolkit.print_line()
            toolkit.print(
                "Run [bold]fastapi cloud unlink[/] first to remove the existing configuration.",
                tag="tip",
            )
            raise typer.Exit(1)

        toolkit.print_title("Link to FastAPI Cloud", tag="FastAPI")
        toolkit.print_line()

        with toolkit.progress("Fetching teams...") as progress:
            with handle_http_errors(
                progress, message="Error fetching teams. Please try again later."
            ):
                with APIClient() as client:
                    response = client.get("/teams/")
                    response.raise_for_status()
                    teams_data = response.json()["data"]

        if not teams_data:
            toolkit.print(
                "[error]No teams found. Please create a team first.[/]",
            )
            raise typer.Exit(1)

        toolkit.print_line()

        team = toolkit.ask(
            "Select the team:",
            tag="team",
            options=[
                Option({"name": t["name"], "value": {"id": t["id"], "name": t["name"]}})
                for t in teams_data
            ],
        )

        toolkit.print_line()

        with toolkit.progress("Fetching apps...") as progress:
            with handle_http_errors(
                progress, message="Error fetching apps. Please try again later."
            ):
                with APIClient() as client:
                    response = client.get("/apps/", params={"team_id": team["id"]})
                    response.raise_for_status()
                    apps_data = response.json()["data"]

        if not apps_data:
            toolkit.print(
                "[error]No apps found in this team.[/]",
            )
            toolkit.print_line()
            toolkit.print(
                "Run [bold]fastapi cloud deploy[/] to create and deploy a new app.",
                tag="tip",
            )
            raise typer.Exit(1)

        toolkit.print_line()

        app = toolkit.ask(
            "Select the app to link:",
            tag="app",
            options=[
                Option({"name": a["slug"], "value": {"id": a["id"], "slug": a["slug"]}})
                for a in apps_data
            ],
        )

        toolkit.print_line()

        app_config = AppConfig(app_id=app["id"], team_id=team["id"])
        write_app_config(path_to_link, app_config)

        toolkit.print(
            f"Successfully linked to app [bold]{app['slug']}[/bold]! 🔗",
        )
        logger.debug(f"Linked to app: {app['id']} in team: {team['id']}")
