import json
from pathlib import Path

import httpx
import pytest
import respx
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.cli import cloud_app as app
from tests.utils import USER_TOKEN, SnapshotCliRunner

runner = SnapshotCliRunner()


@pytest.mark.respx
def test_logout_with_existing_auth_file(
    respx_mock: respx.MockRouter, temp_auth_config: Path
) -> None:
    temp_auth_config.write_text('{"access_token": "test_token"}')

    respx_mock.post("/logout", headers={"Authorization": "Bearer test_token"}).mock(
        return_value=Response(204)
    )

    assert temp_auth_config.exists()

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
FastAPI Cloud

👋 You are now logged out!\
""")

    assert not temp_auth_config.exists()


@pytest.mark.respx
def test_logout_revokes_the_token(
    respx_mock: respx.MockRouter,
    logged_in_cli: None,
    temp_auth_config: Path,
) -> None:
    logout_route = respx_mock.post(
        "/logout",
        headers={"Authorization": f"Bearer {USER_TOKEN}"},
    ).mock(return_value=Response(204))

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert "You are now logged out!" in result.output
    assert not temp_auth_config.exists()

    timeout = logout_route.calls.last.request.extensions["timeout"]
    assert timeout == httpx.Timeout(5).as_dict()


@pytest.mark.respx
@pytest.mark.parametrize(
    "logout_response",
    [
        Response(401),
        Response(500),
        httpx.ConnectError("Connection refused"),
        httpx.ReadTimeout("Timed out"),
    ],
    ids=["unauthorized", "server-error", "network-error", "timeout"],
)
def test_logout_warns_when_the_token_is_not_revoked(
    respx_mock: respx.MockRouter,
    logged_in_cli: None,
    temp_auth_config: Path,
    logout_response: Response | httpx.HTTPError,
) -> None:
    respx_mock.post("/logout").mock(side_effect=[logout_response])

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
FastAPI Cloud

👋 You are now logged out!

⚠️ Couldn't sign out on FastAPI Cloud, so this login stays valid until it
   expires.\
""")
    assert not temp_auth_config.exists()


@pytest.mark.respx
def test_logout_does_not_warn_when_the_server_has_no_logout(
    respx_mock: respx.MockRouter, temp_auth_config: Path
) -> None:
    temp_auth_config.write_text('{"access_token": "test_token"}')

    respx_mock.post("/logout").mock(return_value=Response(404))

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
FastAPI Cloud

👋 You are now logged out!\
""")
    assert not temp_auth_config.exists()


@pytest.mark.respx
def test_logout_with_no_auth_file(
    respx_mock: respx.MockRouter, temp_auth_config: Path
) -> None:
    assert not temp_auth_config.exists()

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert "You are now logged out!" in result.output

    assert not temp_auth_config.exists()
    assert not respx_mock.calls


@pytest.mark.respx
def test_logout_json_with_existing_auth_file(
    respx_mock: respx.MockRouter, temp_auth_config: Path
) -> None:
    temp_auth_config.write_text('{"access_token": "test_token"}')

    respx_mock.post("/logout", headers={"Authorization": "Bearer test_token"}).mock(
        return_value=Response(204)
    )

    result = runner.invoke(app, ["logout", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"logged_out": True}}
    assert result.stderr == ""
    assert not temp_auth_config.exists()


@pytest.mark.respx
def test_logout_json_warns_when_the_token_is_not_revoked(
    respx_mock: respx.MockRouter,
    logged_in_cli: None,
    temp_auth_config: Path,
) -> None:
    respx_mock.post("/logout").mock(side_effect=httpx.ConnectError("Refused"))

    result = runner.invoke(app, ["logout", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"logged_out": True},
        "warnings": [
            {
                "code": "token_not_revoked",
                "message": (
                    "Couldn't sign out on FastAPI Cloud, "
                    "so this login stays valid until it expires."
                ),
            }
        ],
    }
    assert result.stderr == ""
    assert not temp_auth_config.exists()


@pytest.mark.respx
def test_logout_json_with_no_auth_file(
    respx_mock: respx.MockRouter, temp_auth_config: Path
) -> None:
    assert not temp_auth_config.exists()

    result = runner.invoke(app, ["logout", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"logged_out": True}}
    assert result.stderr == ""
    assert not temp_auth_config.exists()
    assert not respx_mock.calls
