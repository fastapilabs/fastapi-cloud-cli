import json
from pathlib import Path

import pytest
import respx
from httpx import ReadTimeout, Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app as root_app
from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.whoami import WhoAmIOutput
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


@pytest.mark.respx
def test_shows_a_message_if_something_is_wrong(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(return_value=Response(500))

    result = runner.invoke(app, ["whoami"])

    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )
    assert result.exit_code == 1


@pytest.mark.respx
def test_shows_a_message_when_token_is_invalid(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(return_value=Response(401))

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 1
    assert "The specified token is not valid" in result.output


@pytest.mark.respx
def test_shows_a_message_when_user_has_no_permissions(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(return_value=Response(403))

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 1
    assert "You don't have permissions for this resource" in result.output


@pytest.mark.respx
def test_shows_email(logged_in_cli: None, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/users/me").mock(
        return_value=Response(200, json={"email": "email@fastapi.com"})
    )

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 0
    assert "email@fastapi.com" in result.output


@pytest.mark.respx
def test_uses_toolkit_output_renderer_for_logged_in_user(
    logged_in_cli: None,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter,
) -> None:
    output_calls: list[tuple[object, object]] = []

    def record_output(
        self: FastAPIRichToolkit,
        data: object,
        render_output: object = None,
    ) -> None:
        output_calls.append((data, render_output))

    monkeypatch.setattr(FastAPIRichToolkit, "output", record_output)
    respx_mock.get("/users/me").mock(
        return_value=Response(200, json={"email": "email@fastapi.com"})
    )

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 0
    assert len(output_calls) == 1
    output_data, render_output = output_calls[0]
    assert isinstance(output_data, WhoAmIOutput)
    assert output_data.model_dump(mode="json") == {
        "email": "email@fastapi.com",
        "has_deploy_token": False,
    }
    assert callable(render_output)


@pytest.mark.respx
def test_prints_json_when_json_env_is_enabled(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(
        return_value=Response(200, json={"email": "email@fastapi.com"})
    )

    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "email": "email@fastapi.com",
            "has_deploy_token": False,
        }
    }
    assert "[bold]" not in result.stdout
    assert result.stderr == ""


def test_json_option_is_not_enabled_before_command(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(root_app, ["cloud", "--json", "whoami"])

    assert result.exit_code == 2
    assert "--json" in result.output


@pytest.mark.respx
def test_prints_json_when_json_option_is_enabled_after_command(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(
        return_value=Response(200, json={"email": "email@fastapi.com"})
    )

    result = runner.invoke(root_app, ["cloud", "whoami", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["email"] == "email@fastapi.com"


def test_prints_json_error_when_json_env_is_enabled_and_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_logged_in",
            "message": "No credentials found.",
            "hint": "Run `fastapi login` or set FASTAPI_CLOUD_TOKEN.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_prints_json_error_when_token_is_invalid(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(return_value=Response(401))

    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_token",
            "message": (
                "The specified token is not valid. "
                "Use `fastapi login` to generate a new token."
            ),
            "hint": "Run `fastapi cloud login` to generate a new token.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_prints_json_error_when_user_has_no_permissions(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(return_value=Response(403))

    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "permission_denied",
            "message": "You don't have permissions for this resource",
            "hint": None,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_prints_json_error_when_request_has_generic_api_error(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(return_value=Response(500))

    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["error"]["code"] == "api_error"
    assert output["error"]["message"].startswith(
        "Something went wrong while contacting the FastAPI Cloud server."
    )
    assert output["error"]["hint"] is None
    assert result.stderr == ""


@pytest.mark.respx
def test_prints_json_error_when_request_times_out(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(side_effect=ReadTimeout)

    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "network_error",
            "message": (
                "The request to the FastAPI Cloud server timed out."
                " Please try again later."
            ),
            "hint": "Please try again later.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_handles_read_timeout(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(side_effect=ReadTimeout)

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 1
    assert "The request to the FastAPI Cloud server timed out" in result.output


def test_prints_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 1
    assert (
        "No credentials found. Run `fastapi login` or set FASTAPI_CLOUD_TOKEN."
        in result.output
    )


def test_prints_not_logged_in_with_deploy_token(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_TOKEN": "ABC"})

    assert result.exit_code == 1
    assert (
        "No credentials found. Run `fastapi login` or set FASTAPI_CLOUD_TOKEN."
        in result.output
    )


@pytest.mark.respx
def test_shows_logged_in_and_has_deploy_token(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/users/me").mock(
        return_value=Response(200, json={"email": "email@fastapi.com"})
    )

    result = runner.invoke(app, ["whoami"], env={"FASTAPI_CLOUD_TOKEN": "ABC"})

    assert result.exit_code == 0
    assert "email@fastapi.com" in result.output
    assert "Using API token from environment variable" in result.output
