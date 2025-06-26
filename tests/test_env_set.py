from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.config import settings
from tests.utils import Keys, changing_dir

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


@pytest.fixture
def configured_app(tmp_path: Path) -> Path:
    app_id = "123"
    team_id = "456"

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    return tmp_path


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


def test_shows_a_message_if_app_is_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 1
    assert "No app found" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_a_message_if_something_is_wrong(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.patch("/apps/123/environment-variables/").mock(
        return_value=Response(500)
    )

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret"])

    assert result.exit_code == 1
    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_message_when_it_sets(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.patch("/apps/123/environment-variables/").mock(
        return_value=Response(200)
    )

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret"])

    assert result.exit_code == 0
    assert "Environment variable SOME_VAR set" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_asks_for_name_and_value(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    steps = [*"SOME_VAR", Keys.ENTER, *"secret", Keys.ENTER]

    respx_mock.patch("/apps/123/environment-variables/").mock(
        return_value=Response(200)
    )

    with changing_dir(configured_app), patch("click.getchar", side_effect=steps):
        result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 0

    assert "Enter the name of the environment variable" in result.output
    assert "Enter the value of the environment variable" in result.output

    assert "Environment variable SOME_VAR set" in result.output

    assert "*" * 6 in result.output
