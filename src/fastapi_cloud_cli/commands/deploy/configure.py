from pathlib import Path

import typer
from pydantic import TypeAdapter
from rich_toolkit.menu import Option

from fastapi_cloud_cli.commands.deploy.archive import AppDirectory, _get_app_name
from fastapi_cloud_cli.commands.deploy.cloud import (
    AppResponse,
    _create_app,
    _get_apps,
    _get_teams,
    _update_app,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import AppConfig, write_app_config
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit


def _configure_app(
    toolkit: FastAPIRichToolkit,
    client: APIClient,
    path_to_deploy: Path,
) -> AppConfig:
    toolkit.print(f"Setting up and deploying [blue]{path_to_deploy}[/blue]", emoji="📁")

    toolkit.print_line()

    with toolkit.progress("Fetching teams...", transient=True) as progress:
        with client.handle_http_errors(
            progress,
            default_message="Error fetching teams. Please try again later.",
        ):
            teams = _get_teams(client)

    team = toolkit.ask(
        "Select the team you want to deploy to:",
        options=[
            Option({"name": team.name, "value": team})
            for team in sorted(teams, key=lambda team: team.name.lower())
        ],
        allow_filtering=True,
        emoji="🏢",
    )

    toolkit.print_line()

    create_new_app = toolkit.confirm(
        "Do you want to create a new app?", default=True, emoji="📦"
    )

    toolkit.print_line()

    selected_app: AppResponse | None = None

    if not create_new_app:
        with toolkit.progress("Fetching apps...", transient=True) as progress:
            with client.handle_http_errors(
                progress,
                default_message="Error fetching apps. Please try again later.",
            ):
                apps = _get_apps(client=client, team_id=team.id)

        if not apps:
            toolkit.fail(
                "not_found",
                "No apps found in this team. You can create a new app instead.",
            )

        selected_app = toolkit.ask(
            "Select the app you want to deploy to:",
            options=[
                Option({"name": app.slug, "value": app})
                for app in sorted(apps, key=lambda app: app.slug.lower())
            ],
            allow_filtering=True,
            emoji="📦",
        )

    app_name = (
        selected_app.slug
        if selected_app
        else toolkit.input(
            title="What's your app name?",
            default=_get_app_name(path_to_deploy),
            emoji="✏️",
        )
    )

    toolkit.print_line()

    initial_directory = selected_app.directory if selected_app else ""

    directory_input = toolkit.input(
        title=(
            "Directory where your app's pyproject.toml file lives (e.g. src, backend):"
        ),
        value=initial_directory or "",
        placeholder=(
            "[italic]Leave empty if pyproject.toml is in the current directory[/italic]"
        ),
        validator=TypeAdapter(AppDirectory),
        emoji="📂",
    )

    directory: str | None = directory_input if directory_input else None

    toolkit.print_line()

    toolkit.print("Deployment configuration:", emoji="📋")
    toolkit.print_line()
    toolkit.print(f"Team: [bold]{team.name}[/bold]")
    toolkit.print(f"App name: [bold]{app_name}[/bold]")
    toolkit.print(f"Directory: [bold]{directory or '.'}[/bold]")

    toolkit.print_line()

    choice = toolkit.ask(
        "Does everything look right?",
        options=[
            Option({"name": "Yes, start the deployment!", "value": "deploy"}),
            Option({"name": "No, let me start over", "value": "cancel"}),
        ],
        emoji="👀",
    )
    toolkit.print_line()

    if choice == "cancel":
        toolkit.print("Deployment cancelled.")
        raise typer.Exit(0)

    if selected_app:
        if directory != selected_app.directory:
            with (
                toolkit.progress(title="Updating app directory...") as progress,
                client.handle_http_errors(progress),
            ):
                app = _update_app(
                    client=client, app_id=selected_app.id, directory=directory
                )

                progress.log(f"App directory updated to '{directory or '.'}'")
        else:
            app = selected_app
    else:
        with toolkit.progress(title="Creating app...") as progress:
            with client.handle_http_errors(progress):
                app = _create_app(
                    client=client,
                    team_id=team.id,
                    app_name=app_name,
                    directory=directory,
                )

            progress.log(f"App created successfully! App slug: {app.slug}")

    app_config = AppConfig(app_id=app.id, team_id=team.id)

    write_app_config(path_to_deploy, app_config)

    return app_config
