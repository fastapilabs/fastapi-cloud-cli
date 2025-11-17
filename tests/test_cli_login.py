import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.config import Settings
from tests.utils import create_jwt_token

runner = CliRunner()
settings = Settings.get()

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
def test_full_login(respx_mock: respx.MockRouter, temp_auth_config: Path) -> None:
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
        ).mock(return_value=Response(200, json={"access_token": "test_token_1234"}))

        # Verify no auth file exists before login
        assert not temp_auth_config.exists()

        result = runner.invoke(app, ["login"])

        assert result.exit_code == 0
        assert mock_open.called
        assert mock_open.call_args.args == ("http://test.com",)
        assert "Now you are logged in!" in result.output

        # Verify auth file was created with correct content
        assert temp_auth_config.exists()
        assert '"access_token":"test_token_1234"' in temp_auth_config.read_text()


@pytest.mark.respx(base_url=settings.base_api_url)
def test_fetch_access_token_success_immediately(respx_mock: respx.MockRouter) -> None:
    from fastapi_cloud_cli.commands.login import _fetch_access_token
    from fastapi_cloud_cli.utils.api import APIClient

    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "test_device_code",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(return_value=Response(200, json={"access_token": "test_token_success"}))

    with APIClient() as client:
        access_token = _fetch_access_token(client, "test_device_code", 5)

    assert access_token == "test_token_success"


@pytest.mark.respx(base_url=settings.base_api_url)
def test_fetch_access_token_authorization_pending_then_success(
    respx_mock: respx.MockRouter,
) -> None:
    from fastapi_cloud_cli.commands.login import _fetch_access_token
    from fastapi_cloud_cli.utils.api import APIClient

    # First call returns authorization pending, second call succeeds
    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "test_device_code",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(
        side_effect=[
            Response(400, json={"error": "authorization_pending"}),
            Response(200, json={"access_token": "test_token_after_pending"}),
        ]
    )

    with patch("fastapi_cloud_cli.commands.login.time.sleep") as mock_sleep:
        with APIClient() as client:
            access_token = _fetch_access_token(client, "test_device_code", 3)

        assert access_token == "test_token_after_pending"
        mock_sleep.assert_called_once_with(3)


@pytest.mark.respx(base_url=settings.base_api_url)
def test_fetch_access_token_handles_400_error_not_authorization_pending(
    respx_mock: respx.MockRouter,
) -> None:
    from fastapi_cloud_cli.commands.login import _fetch_access_token
    from fastapi_cloud_cli.utils.api import APIClient

    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "test_device_code",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(return_value=Response(400, json={"error": "access_denied"}))

    with APIClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            _fetch_access_token(client, "test_device_code", 5)


@pytest.mark.respx(base_url=settings.base_api_url)
def test_fetch_access_token_handles_500_error(respx_mock: respx.MockRouter) -> None:
    from fastapi_cloud_cli.commands.login import _fetch_access_token
    from fastapi_cloud_cli.utils.api import APIClient

    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "test_device_code",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(return_value=Response(500))

    with APIClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            _fetch_access_token(client, "test_device_code", 5)


@pytest.mark.respx(base_url=settings.base_api_url)
def test_notify_already_logged_in_user(
    respx_mock: respx.MockRouter, logged_in_cli: None
) -> None:
    result = runner.invoke(app, ["login"])

    assert result.exit_code == 0
    assert "You are already logged in." in result.output
    assert "Run fastapi logout first if you want to switch accounts." in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_notify_expired_token_user(
    respx_mock: respx.MockRouter, temp_auth_config: Path
) -> None:
    past_exp = int(time.time()) - 3600
    expired_token = create_jwt_token({"sub": "test_user_12345", "exp": past_exp})

    temp_auth_config.write_text(f'{{"access_token": "{expired_token}"}}')

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
        ).mock(return_value=Response(200, json={"access_token": "new_token_1234"}))

        result = runner.invoke(app, ["login"])

        assert result.exit_code == 0
        assert "Your session has expired. Logging in again..." in result.output
        assert "Now you are logged in!" in result.output
        assert mock_open.called
