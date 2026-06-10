from pathlib import Path

from pydantic import BaseModel
from rich.table import Table
from rich.text import Text

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit
from fastapi_cloud_cli.utils.dates import format_last_updated

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
