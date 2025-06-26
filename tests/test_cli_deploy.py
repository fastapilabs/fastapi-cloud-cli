import random
import string
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import patch

import pytest
import respx
from click.testing import Result
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.config import settings
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


def _get_random_team() -> Dict[str, str]:
    name = "".join(random.choices(string.ascii_lowercase, k=10))
    slug = "".join(random.choices(string.ascii_lowercase, k=10))
    id = "".join(random.choices(string.digits, k=10))

    return {"name": name, "slug": slug, "id": id}


def _get_random_app(
    *, slug: Optional[str] = None, team_id: Optional[str] = None
) -> Dict[str, str]:
    name = "".join(random.choices(string.ascii_lowercase, k=10))
    slug = slug or "".join(random.choices(string.ascii_lowercase, k=10))
    id = "".join(random.choices(string.digits, k=10))
    team_id = team_id or "".join(random.choices(string.digits, k=10))

    return {"name": name, "slug": slug, "id": id, "team_id": team_id}


def _get_random_deployment(
    *,
    app_id: Optional[str] = None,
    status: str = "waiting_upload",
) -> Dict[str, str]:
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


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_waitlist_form_when_not_logged_in(
    logged_out_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [*"some@example.com", Keys.ENTER, Keys.RIGHT_ARROW, Keys.ENTER, Keys.ENTER]

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

    with changing_dir(tmp_path), patch(
        "rich_toolkit.menu.click.getchar"
    ) as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

    assert result.exit_code == 1
    assert "We're currently in private beta" in result.output
    assert "Let's go! Thanks for your interest in FastAPI Cloud! 🚀" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_waitlist_form_when_not_logged_in_longer_flow(
    logged_out_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
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

    with changing_dir(tmp_path), patch(
        "rich_toolkit.menu.click.getchar"
    ) as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

    assert result.exit_code == 1
    assert "We're currently in private beta" in result.output
    assert "Let's go! Thanks for your interest in FastAPI Cloud! 🚀" in result.output


def test_asks_to_setup_the_app(logged_in_cli: None, tmp_path: Path) -> None:
    steps = [Keys.RIGHT_ARROW, Keys.ENTER]

    with changing_dir(tmp_path), patch(
        "rich_toolkit.menu.click.getchar"
    ) as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0
        assert "Setup and deploy" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_error_when_trying_to_get_teams(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER]

    respx_mock.get("/teams/").mock(return_value=Response(500))

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "Error fetching teams. Please try again later" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_invalid_auth(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER]

    respx_mock.get("/teams/").mock(return_value=Response(401))

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "The specified token is not valid" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
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

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert team_1["name"] in result.output
        assert team_2["name"] in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
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

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "What's your app name?" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_creates_app_on_backend(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER, Keys.ENTER, Keys.ENTER, *"demo", Keys.ENTER]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [team]},
        )
    )

    respx_mock.post("/apps/", json={"name": "demo", "team_id": team["id"]}).mock(
        return_value=Response(201, json=_get_random_app(team_id=team["id"]))
    )

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "App created successfully" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_uses_existing_app(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [Keys.ENTER, Keys.ENTER, Keys.RIGHT_ARROW, Keys.ENTER, *"demo", Keys.ENTER]

    team = _get_random_team()

    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": [team]}))

    app_data = _get_random_app(team_id=team["id"])

    respx_mock.get("/apps/", params={"team_id": team["id"]}).mock(
        return_value=Response(200, json={"data": [app_data]})
    )

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 1

        assert "Select the app you want to deploy to:" in result.output
        assert app_data["slug"] in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_exits_successfully_when_deployment_is_done(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    steps = [
        Keys.ENTER,
        Keys.ENTER,
        Keys.ENTER,
        *"demo",
        Keys.ENTER,
        Keys.RIGHT_ARROW,
        Keys.ENTER,
    ]

    team_data = _get_random_team()
    app_data = _get_random_app(team_id=team_data["id"])

    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [team_data]})
    )

    respx_mock.post("/apps/", json={"name": "demo", "team_id": team_data["id"]}).mock(
        return_value=Response(201, json=app_data)
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
            json={
                "message": "Hello, world!",
            },
        )
    )

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0

        # TODO: show a message when the deployment is done (based on the status)


@pytest.mark.respx(base_url=settings.base_api_url)
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
            json={
                "message": "All good!",
                "type": "complete",
            },
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
    ).mock(return_value=Response(200))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"])

        assert result.exit_code == 0

        # check that logs are shown
        assert "All good!" in result.output

        # check that the dashboard URL is shown
        assert "You can also check the app logs at" in result.output
        assert deployment_data["dashboard_url"] in result.output

        # check that the app URL is shown
        assert deployment_data["url"] in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
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
            json={
                "message": "Build failed",
                "type": "failed",
            },
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


@pytest.mark.respx(base_url=settings.base_api_url)
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
            json={
                "type": "failed",
                "message": "Build failed",
            },
        )
    )

    respx_mock.post(
        f"/deployments/{deployment_data['id']}/upload-complete",
    ).mock(return_value=Response(200))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["deploy"])

        assert "Something went wrong" in result.stdout

        assert result.exit_code == 1


@pytest.mark.respx(base_url=settings.base_api_url)
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
        Keys.ENTER,
        *"demo",
        Keys.ENTER,
        Keys.RIGHT_ARROW,
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

    respx_mock.post("/apps/", json={"name": "demo", "team_id": team_data["id"]}).mock(
        return_value=Response(201, json=app_data)
    )

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

    with changing_dir(tmp_path), patch("click.getchar") as mock_getchar:
        mock_getchar.side_effect = steps

        return runner.invoke(app, ["deploy", "--no-wait"])


@pytest.mark.respx(base_url=settings.base_api_url)
def test_can_skip_waiting(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    result = _deploy_without_waiting(respx_mock, tmp_path)

    assert result.exit_code == 0

    assert "Check the status of your deployment at" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_creates_config_folder_and_creates_git_ignore(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    _deploy_without_waiting(respx_mock, tmp_path)

    assert (tmp_path / ".fastapicloud" / "cloud.json").exists()
    assert (tmp_path / ".fastapicloud" / "README.md").exists()
    assert (tmp_path / ".fastapicloud" / ".gitignore").read_text() == "*"


@pytest.mark.respx(base_url=settings.base_api_url)
def test_does_not_duplicate_entry_in_git_ignore(
    logged_in_cli: None, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    git_ignore_path = tmp_path / ".gitignore"
    git_ignore_path.write_text(".fastapicloud\n")

    _deploy_without_waiting(respx_mock, tmp_path)

    assert git_ignore_path.read_text() == ".fastapicloud\n"
