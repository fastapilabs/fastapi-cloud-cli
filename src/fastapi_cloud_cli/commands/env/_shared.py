from pathlib import Path

from pydantic import BaseModel
from rich.text import Text

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit

ENV_VAR_VALUE_MAX_LENGTH = 40


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


def _format_env_var_value(env_var: EnvironmentVariable) -> Text:
    if env_var.value is None:
        placeholder = "[secret]" if env_var.is_secret else "-"

        return Text(placeholder, style="dim")

    value = env_var.value.replace("\r", "\\r").replace("\n", "\\n")

    if len(value) > ENV_VAR_VALUE_MAX_LENGTH:
        value = f"{value[: ENV_VAR_VALUE_MAX_LENGTH - 3]}..."

    return Text(value)


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
        hint="Pass --app-id or run `fastapi cloud apps create --link` first.",
    )
