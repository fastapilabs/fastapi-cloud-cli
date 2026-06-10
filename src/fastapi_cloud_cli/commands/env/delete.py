from pathlib import Path
from typing import Annotated, Any

import typer

from fastapi_cloud_cli.commands.env._shared import (
    _delete_environment_variable,
    _get_environment_variables,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.env import validate_environment_variable_name


def delete(
    name: str | None = typer.Argument(
        None,
        help="The name of the environment variable to delete",
    ),
    path: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Path to the directory with your app's pyproject.toml "
                "(defaults to current directory)"
            )
        ),
    ] = None,
) -> Any:
    """
    Delete an environment variable from the app.
    """

    identity = Identity()

    with get_rich_toolkit(minimal=True) as toolkit:
        if not identity.is_logged_in():
            toolkit.print(
                "No credentials found. Use [blue]`fastapi login`[/] to login.",
                tag="auth",
            )

            raise typer.Exit(1)

        path_to_deploy = path or Path.cwd()

        app_config = get_app_config(path_to_deploy)

        if not app_config:
            toolkit.print(
                f"No app found in the folder [bold]{path_to_deploy}[/].",
            )
            raise typer.Exit(1)

        with APIClient() as client:
            if not name:
                with toolkit.progress(
                    "Fetching environment variables...", transient=True
                ) as progress:
                    with client.handle_http_errors(progress):
                        environment_variables = _get_environment_variables(
                            client=client, app_id=app_config.app_id
                        )

                if not environment_variables.data:
                    toolkit.print("No environment variables found.")
                    return

                name = toolkit.ask(
                    "Select the environment variable to delete:",
                    options=[
                        {"name": env_var.name, "value": env_var.name}
                        for env_var in environment_variables.data
                    ],
                )

                assert name
            else:
                if not validate_environment_variable_name(name):
                    toolkit.print(
                        f"The environment variable name [bold]{name}[/] is invalid."
                    )
                    raise typer.Exit(1)

                toolkit.print_line()

            with toolkit.progress(
                "Deleting environment variable", transient=True
            ) as progress:
                with client.handle_http_errors(progress):
                    deleted = _delete_environment_variable(
                        client=client, app_id=app_config.app_id, name=name
                    )

        if not deleted:
            toolkit.print("Environment variable not found.")
            raise typer.Exit(1)

        toolkit.print(f"Environment variable [bold]{name}[/] deleted.")
