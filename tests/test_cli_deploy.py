import random
import string
from datetime import timedelta
from pathlib import Path
from typing import TypedDict
from unittest.mock import patch

import httpx
import pytest
import respx
from click.testing import Result
from httpx import Response
from time_machine import TimeMachineFixture
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.api import StreamLogError, TooManyRetriesError
from tests.conftest import ConfiguredApp
from tests.utils import Keys, build_logs_response, changing_dir, create_jwt_token

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


def _get_random_team() -> dict[str, str]:
    name = "".join(random.choices(string.ascii_lowercase, k=10))
    slug = "".join(random.choices(string.ascii_lowercase, k=10))
    id = "".join(random.choices(string.digits, k=10))

    return {"name": name, "slug": slug, "id": id}


class RandomApp(TypedDict):
    name: str
    slug: str
    id: str
    team_id: str
    directory: str | None


def _get_random_app(
    *,
    slug: str | None = None,
    team_id: str | None = None,
    directory: str | None = None,
) -> RandomApp:
    name = "".join(random.choices(string.ascii_lowercase, k=10))
    slug = slug or "".join(random.choices(string.ascii_lowercase, k=10))
    id = "".join(random.choices(string.digits, k=10))
    team_id = team_id or "".join(random.choices(string.digits, k=10))

    return {
        "name": name,
        "slug": slug,
        "id": id,
        "team_id": team_id,
        "directory": directory,
    }


def _get_random_deployment(
    *,
    app_id: str | None = None,
    status: str = "waiting_upload",
) -> dict[str, str]:
    id = "".join(random.choices(string.digits, k=10))
    slug = "".join(random.choices(string.ascii_lowercase, k=10))
    app_id = app_id or "".join(random.choices(string.digits, k=10))

    return {
        "id": id,
        "app_id": app_id,
        "slug": slug,
        "status": status,
        "url": "http://test.com",
        "dashboard_url": "http://test.com",
    }


@pytest.mark.respx
def test_chooses_login_option_when_not_logged_in(
    logged_out_cli: None,
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    settings: Settings,
) -> None:
    steps = [Keys.ENTER]

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

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
        patch("fastapi_cloud_cli.commands.login.typer.launch") as mock_launch,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

    assert "Welcome to FastAPI Cloud!" in result.output
    assert "What would you like to do?" in result.output
    assert "Login to my existing account" in result.output
    assert "Join the waiting list" in result.output
    assert "Now you are logged in!" in result.output
    assert mock_launch.called


@pytest.mark.respx
def test_chooses_waitlist_option_when_not_logged_in(
    logged_out_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.DOWN_ARROW,
        Keys.ENTER,
        *"some@example.com",
        Keys.ENTER,
        Keys.RIGHT_ARROW,
        Keys.ENTER,
        Keys.ENTER,
    ]

    respx_mock.post(
        "/users/waiting-list",
        json={
            "email": "some@example.com",
            "location": None,
            "name": None,
            "organization": None,
            "role": None,
            "secret_code": None,
            "team_size": None,
            "use_case": None,
        },
    ).mock(return_value=Response(200))

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

    assert result.exit_code == 1
    assert "Welcome to FastAPI Cloud!" in result.output
    assert "What would you like to do?" in result.output
    assert "Login to my existing account" in result.output
    assert "Join the waiting list" in result.output
    assert "We're currently in private beta" in result.output
    assert "Let's go! Thanks for your interest in FastAPI Cloud! 🚀" in result.output


@pytest.mark.respx
def test_shows_waitlist_form_when_not_logged_in_longer_flow(
    logged_out_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.DOWN_ARROW,  # Select "Join the waiting list"
        Keys.ENTER,
        *"some@example.com",
        Keys.ENTER,
        Keys.ENTER,
        # Name
        *"Patrick",
        Keys.TAB,
        # Organization
        *"FastAPI Cloud",
        Keys.TAB,
        # Team
        *"Team A",
        Keys.TAB,
        # Role
        *"Developer",
        Keys.TAB,
        # Location
        *"London",
        Keys.TAB,
        # Use case
        *"I want to build a web app",
        Keys.TAB,
        # Secret code
        *"PyCon Italia",
        Keys.ENTER,
        Keys.ENTER,
    ]

    respx_mock.post(
        "/users/waiting-list",
        json={
            "email": "some@example.com",
            "name": "Patrick",
            "organization": "FastAPI Cloud",
            "role": "Developer",
            "team_size": None,
            "location": "London",
            "use_case": "I want to build a web app",
            "secret_code": "PyCon Italia",
        },
    ).mock(return_value=Response(200))

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

    assert result.exit_code == 1
    assert "We're currently in private beta" in result.output
    assert "Let's go! Thanks for your interest in FastAPI Cloud! 🚀" in result.output


def test_shows_login_prompt_when_token_is_expired(
    temp_auth_config: Path, tmp_path: Path
) -> None:
    expired_token = create_jwt_token({"sub": "test_user", "exp": 0})
    temp_auth_config.write_text(f'{{"access_token": "{expired_token}"}}')

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = [Keys.CTRL_C]
        result = runner.invoke(app, ["deploy"])

    assert "Welcome to FastAPI Cloud!" in result.output
    assert "Your session has expired. Please log in again." in result.output
    assert "What would you like to do?" in result.output


@pytest.mark.respx
def test_shows_error_when_trying_to_get_teams(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER]

    respx_mock.get("/teams/").mock(return_value=Response(500))

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "Error fetching teams. Please try again later" in result.output


@pytest.mark.respx
def test_handles_invalid_auth(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER]

    respx_mock.get("/teams/").mock(return_value=Response(401))

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "The specified token is not valid" in result.output


@pytest.mark.respx
def test_shows_teams(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER, Keys.CTRL_C]

    team_1 = _get_random_team()
    team_2 = _get_random_team()

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [team_1, team_2]},
        )
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert team_1["name"] in result.output
        assert team_2["name"] in result.output


@pytest.mark.respx
def test_asks_for_app_name_after_team(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER, Keys.ENTER, Keys.ENTER, Keys.CTRL_C]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [_get_random_team(), _get_random_team()]},
        )
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "What's your app name?" in result.output


@pytest.mark.respx
def test_creates_app_on_backend(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER, Keys.ENTER, *"demo", Keys.ENTER, Keys.ENTER, Keys.ENTER]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [team]},
        )
    )

    respx_mock.post(
        "/apps/", json={"name": "demo", "team_id": team["id"], "directory": None}
    ).mock(return_value=Response(201, json=_get_random_app(team_id=team["id"])))

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "App created successfully" in result.output


@pytest.mark.respx
def test_creates_app_with_directory(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,
        Keys.ENTER,
        *"demo",
        Keys.ENTER,
        *"src",
        Keys.ENTER,
        Keys.ENTER,
    ]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [team]},
        )
    )

    respx_mock.post(
        "/apps/", json={"name": "demo", "team_id": team["id"], "directory": "src"}
    ).mock(return_value=Response(201, json=_get_random_app(team_id=team["id"])))

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "App created successfully" in result.output
        assert "Directory: src" in result.output


@pytest.mark.respx
@pytest.mark.parametrize(
    "directory,expected_error",
    [
        ("~/src", "cannot start with '~'"),
        ("/absolute/path", "must be a relative path, not absolute"),
        ("src/../etc", "cannot contain '..' path segments"),
        ("src/@app", "contains invalid characters"),
    ],
)
def test_shows_validation_error_for_invalid_directory(
    logged_in_cli: None,
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    directory: str,
    expected_error: str,
) -> None:
    steps = [
        Keys.ENTER,  # Select team
        Keys.ENTER,  # Confirm new app
        *"demo",
        Keys.ENTER,  # App name
        *directory,
        Keys.ENTER,  # Submit invalid directory -> validation error shown
        Keys.CTRL_C,  # Cancel
    ]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [_get_random_team()]},
        )
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert expected_error in result.output


@pytest.mark.respx
def test_cancels_deployment_when_user_selects_no(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,
        Keys.ENTER,
        *"demo",
        Keys.ENTER,
        Keys.ENTER,
        Keys.DOWN_ARROW,
        Keys.ENTER,
    ]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [team]},
        )
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert "Deployment cancelled." in result.output


@pytest.mark.respx
def test_uses_existing_app(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER, Keys.RIGHT_ARROW, Keys.ENTER, *"demo", Keys.ENTER]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": [team]}))

    app_data = _get_random_app(team_id=team["id"])

    respx_mock.get("/apps/", params={"team_id": team["id"]}).mock(
        return_value=Response(200, json={"data": [app_data]})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "Select the app you want to deploy to:" in result.output
        assert app_data["slug"] in result.output


@pytest.mark.respx
def test_uses_existing_app_with_directory(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,  # Select team
        Keys.RIGHT_ARROW,  # Choose existing app (No)
        Keys.ENTER,
        Keys.ENTER,  # Select app from list
        Keys.ENTER,  # Accept pre-filled directory
        Keys.DOWN_ARROW,  # Cancel deployment
        Keys.ENTER,
    ]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": [team]}))

    app_data = _get_random_app(team_id=team["id"], directory="backend")

    respx_mock.get("/apps/", params={"team_id": team["id"]}).mock(
        return_value=Response(200, json={"data": [app_data]})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert "Directory: backend" in result.output


@pytest.mark.respx
def test_uses_existing_app_and_changes_directory(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,  # Select team
        Keys.RIGHT_ARROW,  # Choose existing app (No)
        Keys.ENTER,
        Keys.ENTER,  # Select app from list
        *([Keys.BACKSPACE] * len("backend")),  # Clear pre-filled directory
        *"src",
        Keys.ENTER,  # Submit new directory
        Keys.DOWN_ARROW,  # Cancel deployment
        Keys.ENTER,
    ]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": [team]}))

    app_data = _get_random_app(team_id=team["id"], directory="backend")

    respx_mock.get("/apps/", params={"team_id": team["id"]}).mock(
        return_value=Response(200, json={"data": [app_data]})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert "Directory: src" in result.output


@pytest.mark.respx
def test_updates_app_directory_via_api_when_changed(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,  # Select team
        Keys.RIGHT_ARROW,  # Choose existing app (No)
        Keys.ENTER,
        Keys.ENTER,  # Select app from list
        *([Keys.BACKSPACE] * len("backend")),  # Clear pre-filled directory
        *"src",
        Keys.ENTER,  # Submit new directory
        Keys.ENTER,  # Confirm deployment
    ]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": [team]}))

    app_data = _get_random_app(team_id=team["id"], directory="backend")

    respx_mock.get("/apps/", params={"team_id": team["id"]}).mock(
        return_value=Response(200, json={"data": [app_data]})
    )

    updated_app_data = {**app_data, "directory": "src"}

    patch_route = respx_mock.patch(
        f"/apps/{app_data['id']}", json={"directory": "src"}
    ).mock(return_value=Response(200, json=updated_app_data))

    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=updated_app_data)
    )

    deployment_data = _get_random_deployment(app_id=app_data["id"])

    respx_mock.post(f"/apps/{app_data['id']}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.get(f"/apps/{app_data['id']}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert patch_route.called
        assert "App directory updated" in result.output


@pytest.mark.respx
def test_does_not_update_app_directory_when_unchanged(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,  # Select team
        Keys.RIGHT_ARROW,  # Choose existing app (No)
        Keys.ENTER,
        Keys.ENTER,  # Select app from list
        Keys.ENTER,  # Accept pre-filled directory (unchanged)
        Keys.ENTER,  # Confirm deployment
    ]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": [team]}))

    app_data = _get_random_app(team_id=team["id"], directory="backend")

    respx_mock.get("/apps/", params={"team_id": team["id"]}).mock(
        return_value=Response(200, json={"data": [app_data]})
    )

    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=app_data)
    )

    deployment_data = _get_random_deployment(app_id=app_data["id"])

    respx_mock.post(f"/apps/{app_data['id']}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.get(f"/apps/{app_data['id']}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert "App directory updated" not in result.output


@pytest.mark.respx
def test_exits_successfully_when_deployment_is_done(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,
        Keys.ENTER,
        *"demo",
        Keys.ENTER,
        Keys.ENTER,
        Keys.ENTER,
    ]

    team_data = _get_random_team()
    app_data = _get_random_app(team_id=team_data["id"])

    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [team_data]})
    )

    respx_mock.post(
        "/apps/", json={"name": "demo", "team_id": team_data["id"], "directory": None}
    ).mock(return_value=Response(201, json=app_data))

    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=app_data)
    )

    deployment_data = _get_random_deployment(app_id=app_data["id"])

    respx_mock.post(f"/apps/{app_data['id']}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={
                "url": "http://test.com",
                "fields": {"key": "value"},
            },
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
    ).mock(return_value=Response(200))

    respx_mock.post(
        "http://test.com",
        data={"key": "value"},
    ).mock(return_value=Response(200))

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.get(f"/apps/{app_data['id']}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0


@pytest.mark.respx
def test_exits_successfully_when_deployment_is_done_when_app_is_configured(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "message", "message": "All good!", "id": "2"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
    ).mock(return_value=Response(200))

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0

        # check that logs are shown
        assert "All good!" in result.output

        # check that the app URL is shown
        assert deployment_data["url"] in result.output


@pytest.mark.respx
def test_exits_with_error_when_deployment_fails_to_build(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            json={"type": "failed"},
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
    ).mock(return_value=Response(200))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "Oh no! Something went wrong" in result.output
        assert deployment_data["dashboard_url"] in result.output


@pytest.mark.respx
def test_shows_error_when_deployment_build_fails(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            json={"type": "failed"},
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
    ).mock(return_value=Response(200))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"])

        assert "Something went wrong" in result.stdout

        assert result.exit_code == 1


@pytest.mark.respx
def test_shows_error_when_app_does_not_exist(
    logged_in_cli: None, configured_app: ConfiguredApp, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}").mock(return_value=Response(404))

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "App not found" in result.output


def _deploy_without_waiting(respx_mock: respx.MockRouter, tmp_path: Path) -> Result:
    steps = [
        Keys.ENTER,
        Keys.ENTER,
        *"demo",
        Keys.ENTER,
        Keys.ENTER,
        Keys.ENTER,
    ]

    team_data = _get_random_team()
    app_data = _get_random_app(team_id=team_data["id"])
    deployment_data = _get_random_deployment(app_id=app_data["id"])

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [team_data]},
        )
    )

    respx_mock.post(
        "/apps/", json={"name": "demo", "team_id": team_data["id"], "directory": None}
    ).mock(return_value=Response(201, json=app_data))

    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=app_data)
    )

    respx_mock.post(f"/apps/{app_data['id']}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload",
    ).mock(
        return_value=Response(
            200,
            json={
                "url": "http://test.com",
                "fields": {"key": "value"},
            },
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
    ).mock(return_value=Response(200))

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        return runner.invoke(app, ["deploy", "--no-wait"])


@pytest.mark.respx
def test_can_skip_waiting(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    result = _deploy_without_waiting(respx_mock, tmp_path)

    assert result.exit_code == 0

    assert "Check the status of your deployment at" in result.output


@pytest.mark.respx
def test_creates_config_folder_and_creates_git_ignore(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    _deploy_without_waiting(respx_mock, tmp_path)

    assert (tmp_path / ".fastapicloud" / "cloud.json").exists()
    assert (tmp_path / ".fastapicloud" / "README.md").exists()
    assert (tmp_path / ".fastapicloud" / ".gitignore").read_text() == "*"


@pytest.mark.respx
def test_does_not_duplicate_entry_in_git_ignore(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    git_ignore_path = tmp_path / ".gitignore"
    git_ignore_path.write_text(".fastapicloud\n")

    _deploy_without_waiting(respx_mock, tmp_path)

    assert git_ignore_path.read_text() == ".fastapicloud\n"


@pytest.mark.respx
def test_shows_error_for_invalid_waitlist_form_data(
    logged_out_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.DOWN_ARROW,  # Select "Join the waiting list"
        Keys.ENTER,
        *"test@example.com",
        Keys.ENTER,
        Keys.ENTER,  # Choose to provide more information
        Keys.CTRL_C,  # Interrupt to avoid infinite loop
    ]

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
        patch("rich_toolkit.form.Form.run") as mock_form_run,
    ):
        mock_getchar.side_effect = steps
        # Simulate form returning data with invalid email field to trigger ValidationError
        mock_form_run.return_value = {
            "email": "invalid-email-format",
            "name": "John Doe",
        }

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1
        assert "Invalid form data. Please try again." in result.output


@pytest.mark.respx
def test_shows_no_apps_found_message_when_team_has_no_apps(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,  # Select team
        Keys.RIGHT_ARROW,  # Choose existing app (No)
        Keys.ENTER,
    ]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": [team]}))

    # Mock empty apps list for the team
    respx_mock.get("/apps/", params={"team_id": team["id"]}).mock(
        return_value=Response(200, json={"data": []})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1
        assert (
            "No apps found in this team. You can create a new app instead."
            in result.output
        )


@pytest.mark.parametrize(
    "error",
    [StreamLogError("stream error"), TooManyRetriesError(), TimeoutError()],
)
@pytest.mark.respx
def test_shows_error_message_on_build_exception(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter, error: Exception
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200, json={"url": "http://test.com", "fields": {"key": "value"}}
        )
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.utils.api.APIClient.stream_build_logs",
            side_effect=error,
        ),
    ):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1
        assert "Unable to stream build logs" in result.output
        assert deployment_data["dashboard_url"] in result.output


@pytest.mark.respx
def test_shows_error_message_on_build_log_http_error(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200, json={"url": "http://test.com", "fields": {"key": "value"}}
        )
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(500, text="Internal Server Error")
    )

    with changing_dir(tmp_path), patch("time.sleep"):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1
        assert "Unable to stream build logs" in result.output
        assert deployment_data["dashboard_url"] in result.output


@pytest.mark.respx
@patch("fastapi_cloud_cli.commands.deploy.WAITING_MESSAGES", ["short wait message"])
def test_short_wait_messages(
    logged_in_cli: None,
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    time_machine: TimeMachineFixture,
) -> None:
    time_machine.move_to("2025-11-01 13:00:00", tick=False)
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200, json={"url": "http://test.com", "fields": {"key": "value"}}
        )
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    def build_logs_handler(request: httpx.Request, route: respx.Route) -> Response:
        if route.call_count <= 2:
            time_machine.shift(timedelta(seconds=3))
            return Response(
                200,
                content=build_logs_response(
                    {
                        "type": "message",
                        "message": f"Step {route.call_count}",
                        "id": str(route.call_count),
                    },
                    {"type": "timeout"},
                ),
            )
        else:
            return Response(
                200,
                content=build_logs_response(
                    {"type": "complete"},
                ),
            )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        side_effect=build_logs_handler
    )

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with changing_dir(tmp_path), patch("time.sleep"):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert "Ready the chicken!" in result.output


@pytest.mark.respx
@patch("fastapi_cloud_cli.commands.deploy.LONG_WAIT_MESSAGES", ["long wait message"])
def test_long_wait_messages(
    logged_in_cli: None,
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    time_machine: TimeMachineFixture,
) -> None:
    time_machine.move_to("2025-11-01 13:00:00", tick=False)

    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200, json={"url": "http://test.com", "fields": {"key": "value"}}
        )
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    def build_logs_handler(request: httpx.Request, route: respx.Route) -> Response:
        if route.call_count <= 2:
            time_machine.shift(timedelta(seconds=35))
            return Response(
                200,
                content=build_logs_response(
                    {
                        "type": "message",
                        "message": f"Step {route.call_count}",
                        "id": str(route.call_count),
                    },
                    {"type": "timeout"},
                ),
            )
        else:
            return Response(
                200,
                content=build_logs_response(
                    {"type": "complete"},
                ),
            )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        side_effect=build_logs_handler
    )

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with changing_dir(tmp_path), patch("time.sleep"):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert "Ready the chicken!" in result.output


@pytest.mark.respx
def test_calls_upload_cancelled_when_user_interrupts(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    upload_cancelled_route = respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-cancelled"
    ).mock(return_value=Response(200))

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.commands.deploy._upload_deployment",
            side_effect=KeyboardInterrupt(),
        ),
    ):
        runner.invoke(app, ["deploy"])

        assert upload_cancelled_route.called


@pytest.mark.respx
def test_cancel_upload_swallows_exceptions(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    upload_cancelled_route = respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-cancelled"
    ).mock(return_value=Response(500))

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.commands.deploy._upload_deployment",
            side_effect=KeyboardInterrupt(),
        ),
    ):
        result = runner.invoke(app, ["deploy"])

        assert upload_cancelled_route.called
        assert "HTTPStatusError" not in result.output


@pytest.mark.respx
def test_deploy_successfully_with_token(
    logged_out_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}", headers={"Authorization": "Bearer hello"}).mock(
        return_value=Response(200, json=app_data)
    )

    respx_mock.post(
        f"/apps/{app_id}/deployments/", headers={"Authorization": "Bearer hello"}
    ).mock(return_value=Response(201, json=deployment_data))

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload",
        headers={"Authorization": "Bearer hello"},
    ).mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    respx_mock.get(
        f"/deployments/{deployment_data['id']}/build-logs",
        headers={"Authorization": "Bearer hello"},
    ).mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "message", "message": "All good!", "id": "2"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
        headers={"Authorization": "Bearer hello"},
    ).mock(return_value=Response(200))

    respx_mock.get(
        f"/apps/{app_id}/deployments/{deployment_data['id']}",
        headers={"Authorization": "Bearer hello"},
    ).mock(return_value=Response(200, json={**deployment_data, "status": "success"}))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"], env={"FASTAPI_CLOUD_TOKEN": "hello"})

        assert result.exit_code == 0

        # check that logs are shown
        assert "All good!" in result.output

        # check that the app URL is shown
        assert deployment_data["url"] in result.output


@pytest.mark.respx
def test_deploy_with_token_fails(
    logged_out_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    team_data = _get_random_team()
    app_id = app_data["id"]
    team_id = team_data["id"]

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}", headers={"Authorization": "Bearer hello"}).mock(
        return_value=Response(401, json=app_data)
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"], env={"FASTAPI_CLOUD_TOKEN": "hello"})

        assert result.exit_code == 1

        assert (
            "The specified token is not valid. Make sure to use a valid token."
            in result.output
        )


@pytest.mark.respx
def test_deploy_with_app_id_arg(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy", "--app-id", app_id])

        assert result.exit_code == 0
        assert f"Deploying to app {app_id}" in result.output


@pytest.mark.respx
def test_deploy_with_app_id_from_env_var(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    deployment_data = _get_random_deployment(app_id=app_id)

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"], env={"FASTAPI_CLOUD_APP_ID": app_id})

        assert result.exit_code == 0
        assert f"Deploying to app {app_id}" in result.output


@pytest.mark.respx
def test_deploy_with_app_id_matching_local_config(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    team_id = "some-team-id"
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200,
            json={"url": "http://test.com", "fields": {"key": "value"}},
        )
    )

    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )

    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "complete"},
            ),
        )
    )

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(200, json={**deployment_data, "status": "success"})
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy", "--app-id", app_id])

        assert result.exit_code == 0
        # Should NOT show mismatch warning
        assert "does not match" not in result.output
        assert f"Deploying to app {app_id}" in result.output


@pytest.mark.respx
def test_deploy_with_app_id_mismatch_fails(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    local_app_data = _get_random_app()
    local_app_id = local_app_data["id"]
    team_id = "some-team-id"

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{local_app_id}", "team_id": "{team_id}"}}')

    cli_app_id = "different-app-id"

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy", "--app-id", cli_app_id])

        assert result.exit_code == 1
        assert "does not match" in result.output
        assert "fastapi cloud unlink" in result.output
        assert "FASTAPI_CLOUD_APP_ID" in result.output


@pytest.mark.respx
def test_deploy_with_app_id_arg_app_not_found(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_id = "nonexistent-app-id"

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(404))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy", "--app-id", app_id])

        assert result.exit_code == 1
        assert "App not found" in result.output
        # Should NOT show unlink tip when using --app-id
        assert "unlink" not in result.output


def _setup_deployment_mocks(
    respx_mock: respx.MockRouter,
    app_id: str,
    team_id: str,
    deployment_data: dict[str, str],
    tmp_path: Path,
) -> None:
    """Set up common deployment mocks for a configured app."""
    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    app_data = _get_random_app()
    app_data["id"] = app_id

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200, json={"url": "http://test.com", "fields": {"key": "value"}}
        )
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )
    respx_mock.get(f"/deployments/{deployment_data['id']}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {"type": "message", "message": "Building...", "id": "1"},
                {"type": "complete"},
            ),
        )
    )


@pytest.mark.respx
def test_verification_failure_after_build_complete(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    team_id = "some-team-id"
    deployment_data = _get_random_deployment(app_id=app_id)

    _setup_deployment_mocks(respx_mock, app_id, team_id, deployment_data, tmp_path)

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(
            200, json={**deployment_data, "status": "verifying_failed"}
        )
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1
        assert "Deployment failed" in result.output
        assert "Verifying failed" in result.output
        assert deployment_data["dashboard_url"] in result.output


@pytest.mark.respx
def test_polling_with_intermediate_states(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    team_id = "some-team-id"
    deployment_data = _get_random_deployment(app_id=app_id)

    _setup_deployment_mocks(respx_mock, app_id, team_id, deployment_data, tmp_path)

    call_count = 0

    def poll_handler(request: httpx.Request, route: respx.Route) -> Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return Response(200, json={**deployment_data, "status": "verifying"})
        return Response(200, json={**deployment_data, "status": "success"})

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        side_effect=poll_handler
    )

    with changing_dir(tmp_path), patch("time.sleep"):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert deployment_data["url"] in result.output


@pytest.mark.respx
def test_polling_timeout_shows_dashboard_link(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    team_id = "some-team-id"
    deployment_data = _get_random_deployment(app_id=app_id)

    _setup_deployment_mocks(respx_mock, app_id, team_id, deployment_data, tmp_path)

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.utils.api.APIClient.poll_deployment_status",
            side_effect=TimeoutError("Deployment verification timed out"),
        ),
    ):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert "Could not confirm deployment status" in result.output
        assert deployment_data["dashboard_url"] in result.output


@pytest.mark.respx
def test_verifying_skipped_treated_as_success(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    team_id = "some-team-id"
    deployment_data = _get_random_deployment(app_id=app_id)

    _setup_deployment_mocks(respx_mock, app_id, team_id, deployment_data, tmp_path)

    respx_mock.get(f"/apps/{app_id}/deployments/{deployment_data['id']}").mock(
        return_value=Response(
            200, json={**deployment_data, "status": "verifying_skipped"}
        )
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert deployment_data["url"] in result.output


@pytest.mark.respx
def test_ctrl_c_during_verification_shows_cancelled(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    team_id = "some-team-id"
    deployment_data = _get_random_deployment(app_id=app_id)

    _setup_deployment_mocks(respx_mock, app_id, team_id, deployment_data, tmp_path)

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.utils.api.APIClient.poll_deployment_status",
            side_effect=KeyboardInterrupt(),
        ),
    ):
        result = runner.invoke(app, ["deploy"])

        assert "🟡" in result.output
        assert "Cancelled" in result.output
        assert "✅" not in result.output


@pytest.mark.respx
def test_ctrl_c_during_build_streaming_shows_cancelled(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    app_data = _get_random_app()
    app_id = app_data["id"]
    team_id = "some-team-id"
    deployment_data = _get_random_deployment(app_id=app_id)

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))
    respx_mock.post(f"/apps/{app_id}/deployments/").mock(
        return_value=Response(201, json=deployment_data)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload").mock(
        return_value=Response(
            200, json={"url": "http://test.com", "fields": {"key": "value"}}
        )
    )
    respx_mock.post("http://test.com", data={"key": "value"}).mock(
        return_value=Response(200)
    )
    respx_mock.post(f"/deployments/{deployment_data['id']}/upload-complete").mock(
        return_value=Response(200)
    )

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.utils.api.APIClient.stream_build_logs",
            side_effect=KeyboardInterrupt(),
        ),
    ):
        result = runner.invoke(app, ["deploy"])

        assert "🟡" in result.output
        assert "Cancelled." in result.output
