import logging
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.dates import format_last_updated
from fastapi_cloud_cli.utils.env import validate_environment_variable_name
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)

ENV_VAR_VALUE_MAX_LENGTH = 40
ENVIRONMENT_VARIABLES_TAG = "environment variables"
APP_ID_REQUIRED_HINT = "Pass --app-id or run `fastapi cloud apps create --link` first."


class EnvironmentVariable(BaseModel):
    name: str
    value: str | None = None
    is_secret: bool = False
    updated_at: str | None = None


class EnvironmentVariableResponse(BaseModel):
    data: list[EnvironmentVariable]


class EnvironmentVariablesListOutput(BaseModel):
    app_id: str
    variables: list[EnvironmentVariable]


def _get_environment_variables(
    client: APIClient, app_id: str
) -> EnvironmentVariableResponse:
    response = client.get(f"/apps/{app_id}/environment-variables/")
    response.raise_for_status()

    return EnvironmentVariableResponse.model_validate(response.json())


def _delete_environment_variable(client: APIClient, app_id: str, name: str) -> bool:
    response = client.delete(f"/apps/{app_id}/environment-variables/{name}")

    if response.status_code == 404:
        return False

    response.raise_for_status()

    return True


def _set_environment_variable(
    client: APIClient, app_id: str, name: str, value: str, is_secret: bool = False
) -> None:
    response = client.post(
        f"/apps/{app_id}/environment-variables/",
        json={"name": name, "value": value, "is_secret": is_secret},
    )
    response.raise_for_status()


def _format_env_var_value(env_var: EnvironmentVariable) -> Text:
    if env_var.value is None:
        placeholder = "[secret]" if env_var.is_secret else "-"

        return Text(placeholder, style="dim")

    value = env_var.value.replace("\r", "\\r").replace("\n", "\\n")

    if len(value) > ENV_VAR_VALUE_MAX_LENGTH:
        value = f"{value[: ENV_VAR_VALUE_MAX_LENGTH - 3]}..."

    return Text(value)


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


def _resolve_app_id(
    toolkit: FastAPIRichToolkit, *, app_id: str | None, path: Path | None
) -> str:
    if app_id is not None:
        return app_id

    app_path = path or Path.cwd()
    app_config = get_app_config(app_path)

    if app_config is not None:
        return app_config.app_id

    toolkit.fail(
        "missing_required_input",
        "App ID is required.",
        hint=APP_ID_REQUIRED_HINT,
    )


def _render_environment_variables_list_output(
    data: EnvironmentVariablesListOutput, toolkit: RichToolkit
) -> None:
    toolkit.print_title(ENVIRONMENT_VARIABLES_TAG)
    toolkit.print_line()

    if not data.variables:
        toolkit.print("No environment variables found.", bullet=False)
        return

    toolkit.print(_get_environment_variables_table(data.variables), bullet=False)


env_app = typer.Typer()


@env_app.command("list")
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

        target_app_id = _resolve_app_id(toolkit, app_id=app_id, path=path)

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


@env_app.command()
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


@env_app.command()
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
