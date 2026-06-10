from pathlib import Path
from typing import Annotated, Any

import typer

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit


def _set_environment_variable(
    client: APIClient, app_id: str, name: str, value: str, is_secret: bool = False
) -> None:
    response = client.post(
        f"/apps/{app_id}/environment-variables/",
        json={"name": name, "value": value, "is_secret": is_secret},
    )
    response.raise_for_status()


def set(
    name: str | None = typer.Argument(
        None,
        help="The name of the environment variable to set",
    ),
    value: str | None = typer.Argument(
        None,
        help="The value of the environment variable to set",
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
    secret: Annotated[
        bool,
        typer.Option(
            "--secret",
            help="Mark the environment variable as secret",
        ),
    ] = False,
) -> Any:
    """
    Set an environment variable for the app.
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

        if not name:
            if secret:
                name = toolkit.input("Enter the name of the secret to set:")
            else:
                name = toolkit.input(
                    "Enter the name of the environment variable to set:"
                )

        if not value:
            if secret:
                value = toolkit.input("Enter the secret value:", password=True)
            else:
                value = toolkit.input("Enter the value of the environment variable:")

        with APIClient() as client:
            with toolkit.progress(
                "Setting environment variable", transient=True
            ) as progress:
                assert name is not None
                assert value is not None

                with client.handle_http_errors(progress):
                    _set_environment_variable(
                        client=client,
                        app_id=app_config.app_id,
                        name=name,
                        value=value,
                        is_secret=secret,
                    )

        if secret:
            toolkit.print(f"Secret environment variable [bold]{name}[/] set.")
        else:
            toolkit.print(f"Environment variable [bold]{name}[/] set.")
