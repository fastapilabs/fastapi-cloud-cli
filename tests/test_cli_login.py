from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.config import settings

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_a_message_if_something_is_wrong(respx_mock: respx.MockRouter) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(return_value=Response(500))

        result = runner.invoke(app, ["login"])

        assert result.exit_code == 1
        assert (
            "Something went wrong while contacting the FastAPI Cloud server."
            in result.output
        )

        assert not mock_open.called


@pytest.mark.respx(base_url=settings.base_api_url)
def test_full_login(respx_mock: respx.MockRouter) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(
            return_value=Response(
                200,
                json={
                    "verification_uri_complete": "http://test.com",
                    "verification_uri": "http://test.com",
                    "user_code": "1234",
                    "device_code": "5678",
                },
            )
        )
        respx_mock.post(
            "/login/device/token",
            data={
                "device_code": "5678",
                "client_id": settings.client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        ).mock(return_value=Response(200, json={"access_token": "1234"}))

        result = runner.invoke(app, ["login"])

        assert result.exit_code == 0
        assert mock_open.called
        assert mock_open.call_args.args == ("http://test.com",)
        assert "Now you are logged in!" in result.output
