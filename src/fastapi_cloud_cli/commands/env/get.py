from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich.table import Table
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option

from fastapi_cloud_cli.commands.env._shared import (
    EnvironmentVariable,
    _find_environment_variable,
    _format_env_var_value,
    _get_environment_variables,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class EnvironmentVariableGetOutput(BaseModel):
    app_id: str
    variable: EnvironmentVariable
    show_tag: Annotated[bool, Field(exclude=True)] = True


def _render_environment_variable_get_output(
    data: EnvironmentVariableGetOutput, toolkit: RichToolkit
) -> None:
    variable = data.variable
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column(no_wrap=True)
    table.add_column()
    table.add_row("name:", variable.name)
    table.add_row("value:", _format_env_var_value(variable))

    if data.show_tag:
        toolkit.print_title("environment variables")

    toolkit.print_line()
    toolkit.print(table, bullet=False)


def get_variable(
    name: Annotated[
        str | None,
        typer.Argument(
            help="The name of the environment variable to return.",
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
            help="ID of the app whose environment variable should be returned.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Get an environment variable for the app.
    """

    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        target_app_id = resolve_app_id_or_fail(toolkit, app_id=app_id, path=path)
        name_provided = name is not None

        if name is None and toolkit.mode == "json":
            toolkit.fail(
                "missing_required_input",
                "Environment variable name is required.",
                hint="Pass NAME to choose an environment variable.",
            )

        with APIClient() as client:
            with toolkit.progress(
                "Fetching environment variables...", transient=True
            ) as progress:
                with client.handle_http_errors(progress):
                    environment_variables = _get_environment_variables(
                        client=client, app_id=target_app_id
                    )

        if name is None:
            toolkit.print_title("environment variables")
            toolkit.print_line()

            if not environment_variables.data:
                toolkit.print("No environment variables found.", bullet=False)
                return

            name = toolkit.ask(
                "Select the environment variable to get:",
                options=[
                    Option({"name": env_var.name, "value": env_var.name})
                    for env_var in environment_variables.data
                ],
                bullet=False,
            )

        variable = _find_environment_variable(environment_variables.data, name)

        if variable is None:
            toolkit.fail(
                "not_found",
                f"Environment variable {name} not found.",
                hint="Run `fastapi cloud env list` to see available variables.",
            )
        assert variable is not None

        toolkit.success(
            EnvironmentVariableGetOutput(
                app_id=target_app_id,
                variable=variable,
                show_tag=name_provided,
            ),
            render_output=_render_environment_variable_get_output,
        )
