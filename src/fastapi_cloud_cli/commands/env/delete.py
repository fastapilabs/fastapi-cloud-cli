from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option

from fastapi_cloud_cli.commands.env._shared import _get_environment_variables
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.env import validate_environment_variable_name
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class EnvironmentVariableDeleteOutput(BaseModel):
    app_id: str
    name: str
    deleted: bool = True
    show_tag: Annotated[bool, Field(exclude=True)] = True


def _render_environment_variable_delete_output(
    data: EnvironmentVariableDeleteOutput, toolkit: RichToolkit
) -> None:
    if data.show_tag:
        toolkit.print_title("environment variables")

    toolkit.print_line()
    toolkit.print(f"Environment variable [bold]{data.name}[/] deleted.", bullet=False)


def _delete_environment_variable(client: APIClient, app_id: str, name: str) -> bool:
    response = client.delete(f"/apps/{app_id}/environment-variables/{name}")

    if response.status_code == 404:
        return False

    response.raise_for_status()

    return True


def delete(
    name: str | None = typer.Argument(
        None,
        help="The name of the environment variable to delete",
    ),
    path_arg: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Path to the directory with your app's pyproject.toml "
                "(defaults to current directory)"
            ),
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help=(
                "Path to the directory with your app's pyproject.toml "
                "(defaults to current directory)"
            ),
        ),
    ] = None,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app whose environment variable should be deleted.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Confirm deletion without prompting.",
        ),
    ] = False,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Delete an environment variable from the app.
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
            toolkit, app_id=app_id, path=path or path_arg
        )
        name_provided = name is not None

        with APIClient() as client:
            if not name:
                if toolkit.mode == "json":
                    toolkit.fail(
                        "missing_required_input",
                        "Environment variable name is required.",
                        hint="Pass NAME to choose an environment variable.",
                    )

                with toolkit.progress(
                    "Fetching environment variables...", transient=True
                ) as progress:
                    with client.handle_http_errors(progress):
                        environment_variables = _get_environment_variables(
                            client=client, app_id=target_app_id
                        )

                toolkit.print_title("environment variables")
                toolkit.print_line()

                if not environment_variables.data:
                    toolkit.print("No environment variables found.", bullet=False)
                    return

                name = toolkit.ask(
                    "Select the environment variable to delete:",
                    options=[
                        Option({"name": env_var.name, "value": env_var.name})
                        for env_var in environment_variables.data
                    ],
                    bullet=False,
                )

                assert name
            else:
                if not validate_environment_variable_name(name):
                    toolkit.fail(
                        "invalid_input",
                        f"The environment variable name [bold]{name}[/] is invalid.",
                    )

                toolkit.print_line()

            if name_provided and not yes:
                if toolkit.mode == "json":
                    toolkit.fail(
                        "missing_required_input",
                        "Deletion confirmation is required.",
                        hint="Pass --yes to confirm deletion.",
                    )

                should_delete = toolkit.confirm(
                    f"Delete [bold]{name}[/]?",
                    default=False,
                    bullet=False,
                )
                if not should_delete:
                    toolkit.print_title("environment variables")
                    toolkit.print_line()
                    toolkit.print("Deletion cancelled.", bullet=False)
                    raise typer.Exit(0)
                toolkit.print_line()

            with toolkit.progress(
                "Deleting environment variable", transient=True
            ) as progress:
                with client.handle_http_errors(progress):
                    deleted = _delete_environment_variable(
                        client=client, app_id=target_app_id, name=name
                    )

        if not deleted:
            message = (
                f"Environment variable {name} not found."
                if toolkit.mode == "json"
                else "Environment variable not found."
            )
            toolkit.fail(
                "not_found",
                message,
                hint="Run `fastapi cloud env list` to see available variables.",
            )

        toolkit.success(
            EnvironmentVariableDeleteOutput(
                app_id=target_app_id, name=name, show_tag=name_provided
            ),
            render_output=_render_environment_variable_delete_output,
        )
