from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.env._shared import (
    ENV_VAR_VALUE_MAX_LENGTH,
    EnvironmentVariable,
    _format_env_var_value,
    _get_environment_variables,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.dates import format_last_updated
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class EnvironmentVariablesListOutput(BaseModel):
    app_id: str
    variables: list[EnvironmentVariable]


def _get_environment_variables_table(
    environment_variables: list[EnvironmentVariable],
) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Key", no_wrap=True)
    table.add_column("Value", overflow="ellipsis", max_width=ENV_VAR_VALUE_MAX_LENGTH)
    table.add_column("Last updated", style="dim", no_wrap=True)
    table.add_row("[bold]Key[/bold]", "[bold]Value[/bold]", "[bold]Last updated[/bold]")
    table.add_row("", "", "")

    for env_var in environment_variables:
        table.add_row(
            Text(env_var.name),
            _format_env_var_value(env_var),
            Text(format_last_updated(env_var.updated_at)),
        )

    return table


def _render_environment_variables_list_output(
    data: EnvironmentVariablesListOutput, toolkit: RichToolkit
) -> None:
    toolkit.print_title("environment variables")
    toolkit.print_line()

    if not data.variables:
        toolkit.print("No environment variables found.", bullet=False)
        return

    toolkit.print(_get_environment_variables_table(data.variables), bullet=False)


def list_variables(
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
            help="ID of the app whose environment variables should be listed.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List the environment variables for the app.
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

        with APIClient() as client:
            with toolkit.progress(
                "Fetching environment variables...", transient=True
            ) as progress:
                with client.handle_http_errors(progress):
                    environment_variables = _get_environment_variables(
                        client=client, app_id=target_app_id
                    )

        toolkit.success(
            EnvironmentVariablesListOutput(
                app_id=target_app_id,
                variables=environment_variables.data,
            ),
            render_output=_render_environment_variables_list_output,
        )
