from pathlib import Path
from typing import Annotated, Any, Literal

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

DEFAULT_EXPIRES_IN_DAYS = 365


class CreatedDeployToken(BaseModel):
    id: str
    name: str
    expired_at: str


class DeployTokenCreateAPIResponse(CreatedDeployToken):
    value: str


class StoredDeployTokenSecret(BaseModel):
    provider: Literal["file"] = "file"
    path: Path


class DeployTokenCreateOutput(BaseModel):
    app_id: str
    token: CreatedDeployToken
    stored_secret: StoredDeployTokenSecret
    output_file: Annotated[Path, Field(exclude=True)]


def _resolve_token_name(toolkit: FastAPIRichToolkit, *, name: str | None) -> str:
    if name is not None:
        return name

    if toolkit.mode == "json":
        toolkit.fail(
            "missing_required_input",
            "Deploy token name is required.",
            hint="Pass --name to choose a deploy token name.",
        )

    return toolkit.input(
        "What's the deploy token name?",
        default="Deploy token",
        bullet=False,
    )


def _resolve_output_file(
    toolkit: FastAPIRichToolkit, *, output_file: Path | None
) -> Path:
    if output_file is not None:
        return output_file

    toolkit.fail(
        "missing_required_input",
        "Output file is required.",
        hint="Pass --output-file to store the deploy token value.",
    )


def _create_deploy_token(
    client: APIClient, *, app_id: str, name: str, expires_in_days: int
) -> DeployTokenCreateAPIResponse:
    response = client.post(
        f"/apps/{app_id}/tokens",
        json={"name": name, "expires_in_days": expires_in_days},
    )
    response.raise_for_status()

    return DeployTokenCreateAPIResponse.model_validate(response.json())


def _write_token_value(output_file: Path, value: str) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(value, encoding="utf-8")
    output_file.chmod(0o600)


def _render_deploy_token_create_output(
    data: DeployTokenCreateOutput, toolkit: RichToolkit
) -> None:
    toolkit.print(f"Created deploy token [bold]{data.token.name}[/bold]", bullet=False)
    toolkit.print(
        f"Stored deploy token value in [bold]{data.output_file}[/bold]",
        bullet=False,
    )


def create_token(
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app whose deploy token should be created.",
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option(
            "--name",
            help="Name of the deploy token to create.",
        ),
    ] = None,
    expires_in_days: Annotated[
        int,
        typer.Option(
            "--expires-in-days",
            help="Number of days before the deploy token expires.",
            min=1,
        ),
    ] = DEFAULT_EXPIRES_IN_DAYS,
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output-file",
            help="File path where the deploy token value should be stored.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Create a deploy token for an app.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        target_app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

        toolkit.print_title("deploy tokens")
        toolkit.print_line()

        output_file = _resolve_output_file(toolkit, output_file=output_file)
        name_needs_prompt = name is None
        name = _resolve_token_name(toolkit, name=name)
        if name_needs_prompt:
            toolkit.print_line()

        with APIClient() as client:
            with toolkit.progress(
                title="Creating deploy token",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error creating deploy token. Please try again later.",
                    not_found_message="App not found.",
                    toolkit=toolkit,
                ):
                    token = _create_deploy_token(
                        client,
                        app_id=target_app_id,
                        name=name,
                        expires_in_days=expires_in_days,
                    )

        _write_token_value(output_file, token.value)

        toolkit.success(
            DeployTokenCreateOutput(
                app_id=target_app_id,
                token=CreatedDeployToken.model_validate(token),
                stored_secret=StoredDeployTokenSecret(path=output_file),
                output_file=output_file,
            ),
            render_output=_render_deploy_token_create_output,
        )
