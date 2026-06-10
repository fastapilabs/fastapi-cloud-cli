import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.config import Settings

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


@pytest.mark.respx
def test_shows_a_message_if_something_is_wrong(
    logged_out_cli: None, respx_mock: respx.MockRouter, settings: Settings
) -> None:
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


@pytest.mark.respx
def test_full_login(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(
            return_value=Response(
                200,
                json={
                    "verification_uri_complete": (
                        "http://test.com/device?code=query-code"
                    ),
                    "verification_uri": "http://test.com",
                    "user_code": "manual-code",
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
        assert mock_open.call_args.args == ("http://test.com/device?code=query-code",)
        assert "Now you are logged in!" in result.output

        # Verify auth file was created with correct content
        assert temp_auth_config.exists()
        assert '"access_token":"test_token_1234"' in temp_auth_config.read_text()


@pytest.mark.respx
def test_cloud_auth_login_alias_uses_interactive_login(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(
            return_value=Response(
                200,
                json={
                    "verification_uri_complete": (
                        "http://test.com/device?code=query-code"
                    ),
                    "verification_uri": "http://test.com",
                    "user_code": "manual-code",
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

        result = runner.invoke(app, ["cloud", "auth", "login", "--no-open"])

        assert result.exit_code == 0
        assert "Open http://test.com/device?code=query-code" in result.output
        assert "enter code" not in result.output
        assert "manual-code" not in result.output
        mock_open.assert_not_called()
        assert temp_auth_config.exists()
        assert '"access_token":"test_token_1234"' in temp_auth_config.read_text()


@pytest.mark.respx
def test_cloud_login_json_returns_authorization_data(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(
            return_value=Response(
                200,
                json={
                    "verification_uri_complete": (
                        "http://test.com/device?code=query-code"
                    ),
                    "verification_uri": "http://test.com",
                    "user_code": "manual-code",
                    "device_code": "5678",
                },
            )
        )

        result = runner.invoke(app, ["cloud", "login", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "data": {
                "verification_uri": "http://test.com",
                "verification_uri_complete": ("http://test.com/device?code=query-code"),
                "user_code": "manual-code",
                "device_code": "5678",
                "interval": 5,
            }
        }
        mock_open.assert_not_called()
        assert not temp_auth_config.exists()


@pytest.mark.respx
def test_top_level_login_json_returns_authorization_data(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(
            return_value=Response(
                200,
                json={
                    "verification_uri_complete": (
                        "http://test.com/device?code=query-code"
                    ),
                    "verification_uri": "http://test.com",
                    "user_code": "manual-code",
                    "device_code": "5678",
                },
            )
        )

        result = runner.invoke(app, ["login", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "data": {
                "verification_uri": "http://test.com",
                "verification_uri_complete": ("http://test.com/device?code=query-code"),
                "user_code": "manual-code",
                "device_code": "5678",
                "interval": 5,
            }
        }
        mock_open.assert_not_called()
        assert not temp_auth_config.exists()


def test_auth_start_is_not_supported(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["cloud", "auth", "start"])

    assert result.exit_code != 0
    assert "No such command 'start'" in result.output


@pytest.mark.respx
def test_auth_login_as_json_returns_authorization_data(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(
            return_value=Response(
                200,
                json={
                    "verification_uri_complete": (
                        "http://test.com/device?code=query-code"
                    ),
                    "verification_uri": "http://test.com",
                    "user_code": "manual-code",
                    "device_code": "5678",
                },
            )
        )

        result = runner.invoke(app, ["cloud", "auth", "login", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "data": {
                "verification_uri": "http://test.com",
                "verification_uri_complete": ("http://test.com/device?code=query-code"),
                "user_code": "manual-code",
                "device_code": "5678",
                "interval": 5,
            }
        }
        mock_open.assert_not_called()
        assert not temp_auth_config.exists()


@pytest.mark.respx
def test_auth_wait_as_json_writes_auth_config(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "5678",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(return_value=Response(200, json={"access_token": "test_token_1234"}))

    result = runner.invoke(
        app, ["cloud", "auth", "wait", "--device-code", "5678", "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True, "auth_mode": "user"}
    }
    assert temp_auth_config.exists()
    assert '"access_token":"test_token_1234"' in temp_auth_config.read_text()


@pytest.mark.respx
def test_auth_wait_shows_login_title(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "5678",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(return_value=Response(200, json={"access_token": "test_token_1234"}))

    result = runner.invoke(app, ["cloud", "auth", "wait", "--device-code", "5678"])

    assert result.exit_code == 0
    assert "Login to FastAPI Cloud" in result.output
    assert temp_auth_config.exists()


@pytest.mark.respx
def test_full_login_with_no_open_shows_manual_authorization_details(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
    with patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_open:
        respx_mock.post(
            "/login/device/authorization", data={"client_id": settings.client_id}
        ).mock(
            return_value=Response(
                200,
                json={
                    "verification_uri_complete": (
                        "http://test.com/device?code=query-code"
                    ),
                    "verification_uri": "http://test.com",
                    "user_code": "manual-code",
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

        result = runner.invoke(app, ["cloud", "login", "--no-open"])

        assert result.exit_code == 0
        assert "Open http://test.com/device?code=query-code" in result.output
        assert "enter code" not in result.output
        assert "manual-code" not in result.output
        mock_open.assert_not_called()
        assert temp_auth_config.exists()


@pytest.mark.respx
def test_auth_wait_json_timeout_returns_error_envelope(
    respx_mock: respx.MockRouter,
    temp_auth_config: Path,
    settings: Settings,
) -> None:
    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "5678",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(return_value=Response(400, json={"error": "authorization_pending"}))

    with patch(
        "fastapi_cloud_cli.commands._flow.time.monotonic",
        side_effect=[0.0, 11.0],
    ):
        result = runner.invoke(
            app,
            [
                "cloud",
                "auth",
                "wait",
                "--device-code",
                "5678",
                "--timeout",
                "10",
                "--json",
            ],
        )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "timeout",
            "message": "Login timed out before authorization completed.",
            "hint": "Try again with a longer --timeout value.",
        }
    }
    assert not temp_auth_config.exists()


@pytest.mark.respx
def test_auth_wait_json_cancel_returns_error_envelope(
    temp_auth_config: Path,
) -> None:
    with patch(
        "fastapi_cloud_cli.commands._flow.fetch_access_token",
        side_effect=KeyboardInterrupt,
    ):
        result = runner.invoke(
            app,
            [
                "cloud",
                "auth",
                "wait",
                "--device-code",
                "5678",
                "--json",
            ],
        )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "cancelled",
            "message": "Login cancelled before authorization completed.",
            "hint": "Run `fastapi cloud auth wait --json` again to retry.",
        }
    }
    assert not temp_auth_config.exists()


@pytest.mark.respx
def test_fetch_access_token_uses_default_timeout(
    respx_mock: respx.MockRouter, settings: Settings
) -> None:
    from fastapi_cloud_cli.commands._flow import (
        LoginTimeoutError,
        fetch_access_token,
    )
    from fastapi_cloud_cli.utils.api import APIClient

    respx_mock.post(
        "/login/device/token",
        data={
            "device_code": "test_device_code",
            "client_id": settings.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ).mock(return_value=Response(400, json={"error": "authorization_pending"}))

    with (
        patch(
            "fastapi_cloud_cli.commands._flow.time.monotonic",
            side_effect=[0.0, 301.0],
        ),
        patch(
            "fastapi_cloud_cli.commands._flow.time.sleep",
            side_effect=AssertionError("sleep should not run after timeout"),
        ),
    ):
        with APIClient() as client:
            with pytest.raises(LoginTimeoutError):
                fetch_access_token(client, "test_device_code", 5)


@pytest.mark.respx
def test_full_login_with_deploy_token_set(
    respx_mock: respx.MockRouter, temp_auth_config: Path, settings: Settings
) -> None:
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

        result = runner.invoke(
            app,
            ["login"],
            env={"FASTAPI_CLOUD_TOKEN": "test_deploy_token"},  # Should be ignored
        )

        assert result.exit_code == 0
        assert mock_open.called
        assert mock_open.call_args.args == ("http://test.com",)

        # Verify the warning message is shown
        assert "You have FASTAPI_CLOUD_TOKEN environment variable set." in result.output
        assert "This token will take precedence over the user token" in result.output

        assert "Now you are logged in!" in result.output

        # Verify auth file was created with correct content
        assert temp_auth_config.exists()
        assert '"access_token":"test_token_1234"' in temp_auth_config.read_text()


@pytest.mark.respx
def test_fetch_access_token_success_immediately(
    respx_mock: respx.MockRouter, settings: Settings
) -> None:
    from fastapi_cloud_cli.commands._flow import fetch_access_token
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
        access_token = fetch_access_token(client, "test_device_code", 5)

    assert access_token == "test_token_success"


@pytest.mark.respx
def test_fetch_access_token_authorization_pending_then_success(
    respx_mock: respx.MockRouter,
    settings: Settings,
) -> None:
    from fastapi_cloud_cli.commands._flow import fetch_access_token
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

    with patch("fastapi_cloud_cli.commands._flow.time.sleep") as mock_sleep:
        with APIClient() as client:
            access_token = fetch_access_token(client, "test_device_code", 3)

        assert access_token == "test_token_after_pending"
        mock_sleep.assert_called_once_with(3)


@pytest.mark.respx
def test_fetch_access_token_handles_400_error_not_authorization_pending(
    respx_mock: respx.MockRouter,
    settings: Settings,
) -> None:
    from fastapi_cloud_cli.commands._flow import fetch_access_token
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
            fetch_access_token(client, "test_device_code", 5)


@pytest.mark.respx
def test_fetch_access_token_handles_500_error(
    respx_mock: respx.MockRouter, settings: Settings
) -> None:
    from fastapi_cloud_cli.commands._flow import fetch_access_token
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
            fetch_access_token(client, "test_device_code", 5)


@pytest.mark.respx
def test_notify_already_logged_in_user(
    respx_mock: respx.MockRouter, logged_in_cli: None
) -> None:
    result = runner.invoke(app, ["login"])

    assert result.exit_code == 0
    assert "You are already logged in." in result.output
    assert (
        "Run fastapi cloud logout first if you want to switch accounts."
        in result.output
    )
