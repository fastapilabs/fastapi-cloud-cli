import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.config import Settings
from tests.conftest import ConfiguredApp
from tests.utils import changing_dir

runner = CliRunner()
settings = Settings.get()


def test_shows_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["logs"])

    assert result.exit_code == 1
    assert "No credentials found" in result.output


def test_shows_message_if_app_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["logs"])

    assert result.exit_code == 1
    assert "No app linked to this directory" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_displays_logs(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    log_lines = [
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:01.123000Z",
                "message": "Application startup complete",
                "level": "info",
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:05.456000Z",
                "message": "GET /health 200",
                "level": "info",
            }
        ),
    ]
    response_content = "\n".join(log_lines)

    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(200, content=response_content)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 0
    assert "Fetching logs" in result.output
    assert configured_app.app_id in result.output
    assert "Application startup complete" in result.output
    assert "GET /health 200" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_passes_default_params(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    route = respx_mock.get(
        url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*"
    ).mock(return_value=httpx.Response(200, content=""))

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs"])

    assert result.exit_code == 0
    url = str(route.calls[0].request.url).lower()
    assert "follow=true" in url
    assert "tail=100" in url
    assert "since=5m" in url
    assert "Streaming logs" in result.output
    assert configured_app.app_id in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_passes_custom_params(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    route = respx_mock.get(
        url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*"
    ).mock(return_value=httpx.Response(200, content=""))

    with changing_dir(configured_app.path):
        result = runner.invoke(
            app, ["logs", "--no-follow", "--tail", "50", "--since", "1h"]
        )

    assert result.exit_code == 0
    url = str(route.calls[0].request.url).lower()
    assert "tail=50" in url
    assert "since=1h" in url
    assert "follow=false" in url


@pytest.mark.respx(base_url=settings.base_api_url)
def test_displays_all_log_levels(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    log_lines = [
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:01.123000Z",
                "message": "Debug message",
                "level": "debug",
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:02.123000Z",
                "message": "Info message",
                "level": "info",
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:03.123000Z",
                "message": "Warning message",
                "level": "warning",
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:04.123000Z",
                "message": "Error message",
                "level": "error",
            }
        ),
    ]
    response_content = "\n".join(log_lines)

    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(200, content=response_content)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 0
    assert "Debug message" in result.output
    assert "Info message" in result.output
    assert "Warning message" in result.output
    assert "Error message" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_401_unauthorized(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(401)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 1
    assert "token is not valid" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_404(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(404)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 1
    assert "App not found" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_500_server_error(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(500)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 1
    assert "Failed to fetch logs" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_read_timeout(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        side_effect=httpx.ReadTimeout("Connection timed out")
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 1
    assert "timed out" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_connection_error(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        side_effect=httpx.ConnectError("Connection failed")
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 1
    assert "Failed to fetch logs" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_message_when_no_logs_found(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(200, content="")
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 0
    assert "No logs found" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_server_error_message(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    log_lines = [
        json.dumps({"type": "error", "message": "Log storage unavailable"}),
    ]
    response_content = "\n".join(log_lines)

    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(200, content=response_content)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 1
    assert "Log storage unavailable" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_unknown_log_level(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    log_lines = [
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:01.123000Z",
                "message": "Unknown level message",
                "level": "custom_level",
            }
        ),
    ]
    response_content = "\n".join(log_lines)

    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(200, content=response_content)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 0
    assert "Unknown level message" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_skips_invalid_json_lines(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    log_lines = [
        "not valid json",
        json.dumps(
            {
                "timestamp": "2025-12-05T14:32:01.123000Z",
                "message": "Valid log message",
                "level": "info",
            }
        ),
    ]
    response_content = "\n".join(log_lines)

    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        return_value=httpx.Response(200, content=response_content)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs", "--no-follow"])

    assert result.exit_code == 0
    assert "Valid log message" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_gives_up_after_max_reconnect_attempts(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    """Test that follow mode gives up after max reconnection attempts."""
    respx_mock.get(url__regex=rf"/apps/{configured_app.app_id}/logs/stream.*").mock(
        side_effect=httpx.ConnectError("Connection failed")
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["logs"])

    assert result.exit_code == 1
    assert "Lost connection" in result.output
