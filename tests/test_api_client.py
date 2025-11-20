from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
import respx
from httpx import Response
from time_machine import TimeMachineFixture

from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.api import (
    BUILD_LOG_MAX_RETRIES,
    APIClient,
    BuildLogError,
    BuildLogLineMessage,
    TooManyRetriesError,
)
from tests.utils import build_logs_response

settings = Settings.get()


@pytest.fixture
def client() -> httpx.Client:
    """Create an HTTP client for testing."""
    return APIClient()


@pytest.fixture
def deployment_id() -> str:
    return "test-deployment-123"


api_mock = respx.mock(base_url=settings.base_api_url)


@pytest.fixture
def logs_route(deployment_id: str) -> respx.Route:
    return api_mock.get(f"/deployments/{deployment_id}/build-logs")


@api_mock
def test_stream_build_logs_successful(
    logs_route: respx.Route,
    client: APIClient,
    deployment_id: str,
) -> None:
    logs_route.mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "message", "message": "Done!", "id": "2"},
                {"type": "complete", "id": "3"},
            ),
        )
    )

    logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 3

    assert logs[0].type == "message"
    assert logs[0].message == "Building..."

    assert logs[1].type == "message"
    assert logs[1].message == "Done!"

    assert logs[2].type == "complete"


@api_mock
def test_stream_build_logs_failed(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    logs_route.mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Error occurred", "id": "1"},
                {"type": "failed", "id": "2"},
            ),
        )
    )

    logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 2
    assert logs[0].type == "message"
    assert logs[1].type == "failed"


@pytest.mark.parametrize("terminal_type", ["complete", "failed"])
@api_mock
def test_stream_build_logs_stop_after_terminal_state(
    logs_route: respx.Route,
    client: APIClient,
    terminal_type: str,
    deployment_id: str,
) -> None:
    logs_route.mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Step 1", "id": "1"},
                {"type": terminal_type, "id": "2"},
                {"type": "message", "message": "This should not appear", "id": "3"},
            ),
        )
    )

    logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 2
    assert logs[0].type == "message"
    assert logs[1].type == terminal_type


@api_mock
def test_stream_build_logs_internal_messages_are_skipped(
    logs_route: respx.Route,
    client: APIClient,
    deployment_id: str,
) -> None:
    logs_route.mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "heartbeat", "id": "1"},
                {"type": "message", "message": "Continuing...", "id": "2"},
                {"type": "complete", "id": "3"},
            ),
        )
    )

    logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 2
    assert logs[0].type == "message"
    assert logs[1].type == "complete"


@api_mock
def test_stream_build_logs_malformed_json_is_skipped(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    content = "\n".join(
        [
            '{"type": "message", "message": "Valid", "id": "1"}',
            "not valid json",
            '{"type": "complete", "id": "2"}',
        ]
    )

    logs_route.mock(return_value=Response(200, content=content))

    logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 2
    assert logs[0].type == "message"
    assert logs[1].type == "complete"


@api_mock
def test_stream_build_logs_unknown_log_type_is_skipped(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    logs_route.mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "unknown_future_type", "id": "1"},
                {"type": "message", "message": "Valid", "id": "2"},
                {"type": "complete", "id": "3"},
            ),
        )
    )

    logs = list(client.stream_build_logs(deployment_id))

    # Unknown type should be filtered out
    assert len(logs) == 2
    assert logs[0].type == "message"
    assert logs[1].type == "complete"


@pytest.mark.parametrize(
    "network_error",
    [httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError],
)
@api_mock
def test_stream_build_logs_network_error_retry(
    logs_route: respx.Route,
    client: APIClient,
    network_error: Exception,
    deployment_id: str,
) -> None:
    # First call fails, second succeeds
    logs_route.side_effect = [
        network_error,
        network_error,
        Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Success after retry", "id": "1"},
                {"type": "complete", "id": "2"},
            ),
        ),
    ]

    with patch("time.sleep"):
        logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 2
    assert logs[0].type == "message"
    assert logs[0].message == "Success after retry"


@api_mock
def test_stream_build_logs_server_error_retry(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    logs_route.side_effect = [
        Response(500, text="Internal Server Error"),
        Response(
            200,
            content=build_logs_response(
                {"type": "complete", "id": "1"},
            ),
        ),
    ]

    with patch("time.sleep"):
        logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 1
    assert logs[0].type == "complete"


@api_mock
def test_stream_build_logs_client_error_raises_immediately(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    logs_route.mock(return_value=Response(404, text="Not Found"))

    with pytest.raises(BuildLogError, match="HTTP 404"):
        list(client.stream_build_logs(deployment_id))


@api_mock
def test_stream_build_logs_max_retries_exceeded(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    logs_route.side_effect = httpx.NetworkError("Connection failed")

    with patch("time.sleep"):
        with pytest.raises(
            TooManyRetriesError, match=f"Failed after {BUILD_LOG_MAX_RETRIES} attempts"
        ):
            list(client.stream_build_logs(deployment_id))


@api_mock
def test_stream_build_logs_empty_lines_are_skipped(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    content = "\n".join(
        [
            "",
            '{"type": "message", "message": "Valid", "id": "1"}',
            "   ",
            '{"type": "complete", "id": "2"}',
            "",
        ]
    )

    logs_route.mock(return_value=Response(200, content=content))

    logs = list(client.stream_build_logs(deployment_id))

    assert len(logs) == 2
    assert logs[0].type == "message"
    assert logs[1].type == "complete"


@respx.mock(base_url=settings.base_api_url)
def test_stream_build_logs_continue_after_timeout(
    respx_mock: respx.MockRouter,
    client: APIClient,
    deployment_id: str,
) -> None:
    for id, last_id in enumerate([None, "1", "2"], start=1):
        params = {"last_id": last_id} if last_id else {}
        message = f"message {id}"

        respx_mock.get(
            f"/deployments/{deployment_id}/build-logs", params__eq=params
        ).mock(
            return_value=Response(
                200,
                content=build_logs_response(
                    {"type": "message", "message": message, "id": str(id)},
                    {"type": "timeout"},
                ),
            )
        )

    respx_mock.get(
        f"/deployments/{deployment_id}/build-logs", params__eq={"last_id": "3"}
    ).mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "message 4", "id": "4"},
                {"type": "complete", "id": "5"},
            ),
        )
    )

    logs = client.stream_build_logs(deployment_id)

    with patch("time.sleep"):
        assert next(logs) == BuildLogLineMessage(message="message 1", id="1")
        assert next(logs) == BuildLogLineMessage(message="message 2", id="2")
        assert next(logs) == BuildLogLineMessage(message="message 3", id="3")
        assert next(logs) == BuildLogLineMessage(message="message 4", id="4")
        assert next(logs).type == "complete"


@api_mock
def test_stream_build_logs_connection_closed_without_complete_failed_or_timeout(
    logs_route: respx.Route, client: APIClient, deployment_id: str
) -> None:
    logs_route.mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "hello", "id": "1"},
            ),
        )
    )

    logs = client.stream_build_logs(deployment_id)

    with patch("time.sleep"), pytest.raises(TooManyRetriesError, match="Failed after"):
        for _ in range(BUILD_LOG_MAX_RETRIES + 1):
            next(logs)


@api_mock
def test_stream_build_logs_retry_timeout(
    logs_route: respx.Route,
    client: APIClient,
    time_machine: TimeMachineFixture,
    deployment_id: str,
) -> None:
    time_machine.move_to("2025-11-01 13:00:00", tick=False)

    def responses(request: httpx.Request, route: respx.Route) -> Response:
        time_machine.shift(timedelta(hours=1))

        return Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "First", "id": "1"},
            ),
        )

    logs_route.mock(side_effect=responses)

    with patch("time.sleep"), pytest.raises(TimeoutError, match="timed out"):
        list(client.stream_build_logs(deployment_id))
