from pathlib import Path

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.config import settings
from tests.conftest import ConfiguredApp
from tests.utils import changing_dir

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


def test_shows_a_message_if_app_is_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert "No app found" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_a_message_if_something_is_wrong(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(500)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_a_message_if_no_env_variables(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": []})
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert "No environment variables found." in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_environment_variables_names(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"name": "SECRET_KEY", "value": "123"},
                    {"name": "API_KEY", "value": "456"},
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert "SECRET_KEY" in result.output
    assert "API_KEY" in result.output
