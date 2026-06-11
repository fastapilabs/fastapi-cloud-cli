import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class EnvironmentVariableSetOutput(BaseModel):
    app_id: str
    name: str
    is_secret: bool
    show_tag: Annotated[bool, Field(exclude=True)] = True


def _render_environment_variable_set_output(
    data: EnvironmentVariableSetOutput, toolkit: RichToolkit
) -> None:
    kind = "Secret environment variable" if data.is_secret else "Environment variable"
    message = f"{kind} [bold]{data.name}[/] set."

    if data.show_tag:
        toolkit.print_title("environment variables")

    toolkit.print_line()
    toolkit.print(message, bullet=False)


def _input(
    toolkit: FastAPIRichToolkit,
    prompt: str,
    *,
    password: bool = False,
) -> str:
    return toolkit.input(prompt, password=password, bullet=False)


def _resolve_environment_variable_name(
    toolkit: FastAPIRichToolkit, *, name: str | None, secret: bool
) -> str:
    if name is not None:
        return name

    if toolkit.mode == "json":
        toolkit.fail(
            "missing_required_input",
            "Environment variable name is required.",
            hint="Pass NAME to choose an environment variable.",
        )

    if secret:
        return _input(toolkit, "Enter the name of the secret to set:")

    return _input(toolkit, "Enter the name of the environment variable to set:")


def _resolve_environment_variable_value(
    toolkit: FastAPIRichToolkit,
    *,
    value: str | None,
    value_stdin: bool,
    secret: bool,
) -> str:
    if value is not None and value_stdin:
        toolkit.fail(
            "invalid_input",
            "Only one environment variable value source can be used.",
            hint="Pass either VALUE or --value-stdin.",
        )

    if value is not None:
        return value

    if value_stdin:
        return sys.stdin.read().rstrip("\r\n")

    if toolkit.mode == "json":
        toolkit.fail(
            "missing_required_input",
            "Environment variable value is required.",
            hint="Pass VALUE or --value-stdin to set the environment variable.",
        )

    if secret:
        return _input(toolkit, "Enter the secret value:", password=True)

    return _input(toolkit, "Enter the value of the environment variable:")


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
    path_arg: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Path to the directory with your app's pyproject.toml "
                "(defaults to current directory)"
            )
        ),
    ] = None,
    value_stdin: Annotated[
        bool,
        typer.Option(
            "--value-stdin",
            help="Read the environment variable value from stdin.",
        ),
    ] = False,
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
            help="ID of the app whose environment variable should be set.",
        ),
    ] = None,
    secret: Annotated[
        bool,
        typer.Option(
            "--secret",
            help="Mark the environment variable as secret",
        ),
    ] = False,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Set an environment variable for the app.
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
        name_needs_prompt = name is None
        value_needs_prompt = value is None and not value_stdin
        prompts_user = name_needs_prompt or value_needs_prompt
        if prompts_user and toolkit.mode != "json":
            toolkit.print_title("environment variables")
            toolkit.print_line()

        name = _resolve_environment_variable_name(
            toolkit,
            name=name,
            secret=secret,
        )
        value = _resolve_environment_variable_value(
            toolkit,
            value=value,
            value_stdin=value_stdin,
            secret=secret,
        )

        with APIClient() as client:
            with toolkit.progress(
                "Setting environment variable", transient=True
            ) as progress:
                with client.handle_http_errors(progress):
                    _set_environment_variable(
                        client=client,
                        app_id=target_app_id,
                        name=name,
                        value=value,
                        is_secret=secret,
                    )

        toolkit.success(
            EnvironmentVariableSetOutput(
                app_id=target_app_id,
                name=name,
                is_secret=secret,
                show_tag=not prompts_user,
            ),
            render_output=_render_environment_variable_set_output,
        )
