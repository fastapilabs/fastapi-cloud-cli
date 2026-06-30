import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
import time_machine
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.apps.list import (
    App,
    _get_app_dashboard_url,
)
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.apps import AppConfig
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()


def test_creates_app_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "apps",
            "create",
            "--team-id",
            "00000000-0000-4000-8000-000000000001",
            "--name",
            "API",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_logged_in",
            "message": "No credentials found.",
            "hint": "Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_creates_app_as_json_without_link_by_default(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": "backend",
    }
    respx_mock.post(
        "/apps/",
        json={"team_id": team_id, "name": "API", "directory": "backend"},
    ).mock(return_value=Response(201, json=app_data))

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            [
                "apps",
                "create",
                "--team-id",
                team_id,
                "--name",
                "API",
                "--directory",
                "backend",
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app": app_data,
            "linked": False,
        }
    }
    assert not (tmp_path / ".fastapicloud" / "cloud.json").exists()
    assert result.stderr == ""


@pytest.mark.respx
def test_creates_app_and_links_to_path_when_link_is_explicit(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": "backend",
    }
    path_to_link = tmp_path / "repo"
    path_to_link.mkdir()
    config_path = path_to_link / ".fastapicloud" / "cloud.json"
    respx_mock.post(
        "/apps/",
        json={"team_id": team_id, "name": "API", "directory": "backend"},
    ).mock(return_value=Response(201, json=app_data))

    result = runner.invoke(
        app,
        [
            "apps",
            "create",
            "--team-id",
            team_id,
            "--name",
            "API",
            "--directory",
            "backend",
            "--link",
            "--path",
            str(path_to_link),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app": app_data,
            "linked": True,
        }
    }
    assert AppConfig.model_validate_json(config_path.read_text(encoding="utf-8")) == (
        AppConfig(app_id=app_id, team_id=team_id)
    )
    assert result.stderr == ""


@pytest.mark.respx
def test_creates_app_prompts_for_team_when_team_id_is_missing(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    team_data = {
        "id": team_id,
        "slug": "acme",
        "name": "Acme",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [team_data], "count": 1})
    )
    respx_mock.post(
        "/apps/",
        json={"team_id": team_id, "name": "API", "directory": None},
    ).mock(return_value=Response(201, json=app_data))

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = [Keys.ENTER]
        result = runner.invoke(app, ["apps", "create", "--name", "API", "--no-link"])

    assert result.exit_code == 0
    assert "Select the team:" in result.output
    assert "Acme" in result.output
    assert "Created app API" in result.output
    assert not (tmp_path / ".fastapicloud" / "cloud.json").exists()


@pytest.mark.respx
def test_creates_app_prompts_for_name_and_links_by_default(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    path_to_link = tmp_path / "repo"
    path_to_link.mkdir()
    config_path = path_to_link / ".fastapicloud" / "cloud.json"
    respx_mock.post(
        "/apps/",
        json={"team_id": team_id, "name": "API", "directory": None},
    ).mock(return_value=Response(201, json=app_data))

    with patch("rich_toolkit.container.getchar") as mock_getchar:
        mock_getchar.side_effect = [*"API", Keys.ENTER]
        result = runner.invoke(
            app,
            [
                "apps",
                "create",
                "--team-id",
                team_id,
                "--path",
                str(path_to_link),
            ],
        )

    assert result.exit_code == 0
    assert "What's your app name?" in result.output
    assert "Created app API" in result.output
    assert "Linked" in result.output
    # join wrapped lines: where the message wraps depends on the tmp path length
    assert "to API" in " ".join(result.output.split())
    assert AppConfig.model_validate_json(config_path.read_text(encoding="utf-8")) == (
        AppConfig(app_id=app_id, team_id=team_id)
    )


@pytest.mark.parametrize(
    ("args", "message", "hint"),
    [
        (
            ["--name", "API"],
            "Team ID is required.",
            "Pass --team-id to choose a team.",
        ),
        (
            ["--team-id", "00000000-0000-4000-8000-000000000001"],
            "App name is required.",
            "Pass --name to choose an app name.",
        ),
    ],
)
def test_creates_app_json_requires_team_id_and_name(
    logged_in_cli: None,
    args: list[str],
    message: str,
    hint: str,
) -> None:
    result = runner.invoke(app, ["apps", "create", *args, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": message,
            "hint": hint,
        }
    }
    assert result.stderr == ""


def test_creates_app_json_rejects_path_without_link(
    logged_in_cli: None,
    settings: Settings,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    path_to_link = tmp_path / "repo"
    path_to_link.mkdir()

    with respx.mock(base_url=settings.base_api_url, assert_all_called=False) as router:
        router.post(
            "/apps/",
            json={"team_id": team_id, "name": "API", "directory": None},
        ).mock(return_value=Response(201, json=app_data))

        result = runner.invoke(
            app,
            [
                "apps",
                "create",
                "--team-id",
                team_id,
                "--name",
                "API",
                "--path",
                str(path_to_link),
                "--json",
            ],
        )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "Path can only be used when linking.",
            "hint": "Pass --link or omit --path.",
        }
    }
    assert not (path_to_link / ".fastapicloud" / "cloud.json").exists()
    assert result.stderr == ""


def test_creates_app_json_rejects_invalid_directory(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        [
            "apps",
            "create",
            "--team-id",
            "00000000-0000-4000-8000-000000000001",
            "--name",
            "API",
            "--directory",
            "/tmp/api",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": ("Invalid app directory: must be a relative path, not absolute"),
            "hint": (
                "Pass a relative app directory such as `src` or `backend`; "
                "use --path with --link to choose a local filesystem path."
            ),
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_updates_app_directory_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    app_data = {
        "id": app_id,
        "team_id": "00000000-0000-4000-8000-000000000001",
        "slug": "api",
        "name": "API",
        "directory": "backend",
    }
    respx_mock.patch(
        f"/apps/{app_id}",
        json={"directory": "backend"},
    ).mock(return_value=Response(200, json=app_data))

    result = runner.invoke(
        app,
        [
            "apps",
            "update",
            app_id,
            "--directory",
            "backend",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"app": app_data}}
    assert result.stderr == ""


@pytest.mark.respx
def test_updates_linked_app_directory_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    app_data = {
        "id": configured_app.app_id,
        "team_id": configured_app.team_id,
        "slug": "api",
        "name": "API",
        "directory": "src",
    }
    respx_mock.patch(
        f"/apps/{configured_app.app_id}",
        json={"directory": "src"},
    ).mock(return_value=Response(200, json=app_data))

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["apps", "update", "--directory", "src"])

    assert result.exit_code == 0
    assert "Updated app API" in result.output
    assert "Directory: src" in result.output


def test_updates_app_json_returns_missing_required_input_without_update_flags(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "apps",
            "update",
            "00000000-0000-4000-8000-000000000002",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "No updates provided.",
            "hint": "Pass --directory to update the app directory.",
        }
    }
    assert result.stderr == ""


def test_updates_app_json_rejects_invalid_directory(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        [
            "apps",
            "update",
            "00000000-0000-4000-8000-000000000002",
            "--directory",
            "/tmp/api",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": ("Invalid app directory: must be a relative path, not absolute"),
            "hint": "Pass a relative app directory such as `src` or `backend`.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_links_existing_app_to_path_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    path_to_link = tmp_path / "repo"
    path_to_link.mkdir()
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    result = runner.invoke(
        app,
        [
            "apps",
            "link",
            app_id,
            "--path",
            str(path_to_link),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "team_id": team_id,
            "path": str(path_to_link),
        }
    }
    assert AppConfig.model_validate_json(
        (path_to_link / ".fastapicloud" / "cloud.json").read_text(encoding="utf-8")
    ) == AppConfig(app_id=app_id, team_id=team_id)
    assert result.stderr == ""


def test_links_existing_app_returns_already_linked_without_force(
    logged_in_cli: None,
    tmp_path: Path,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    path_to_link = tmp_path / "repo"
    config_path = path_to_link / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        AppConfig(app_id="existing-app", team_id="existing-team").model_dump_json(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "apps",
            "link",
            app_id,
            "--path",
            str(path_to_link),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "already_linked",
            "message": "This directory is already linked to an app.",
            "hint": "Pass --force to replace the existing configuration.",
        }
    }
    assert AppConfig.model_validate_json(config_path.read_text(encoding="utf-8")) == (
        AppConfig(app_id="existing-app", team_id="existing-team")
    )
    assert result.stderr == ""


@pytest.mark.respx
def test_links_existing_app_replaces_config_with_force(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    path_to_link = tmp_path / "repo"
    config_path = path_to_link / ".fastapicloud" / "cloud.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        AppConfig(app_id="existing-app", team_id="existing-team").model_dump_json(),
        encoding="utf-8",
    )
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    result = runner.invoke(
        app,
        [
            "apps",
            "link",
            app_id,
            "--path",
            str(path_to_link),
            "--force",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "team_id": team_id,
            "path": str(path_to_link),
        }
    }
    assert AppConfig.model_validate_json(config_path.read_text(encoding="utf-8")) == (
        AppConfig(app_id=app_id, team_id=team_id)
    )
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_apps_as_json_with_team_and_pagination_params(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    team_data = {
        "id": team_id,
        "slug": "strawberry",
        "name": "Strawberry",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://strawberryrocks.fastapicloud.dev",
        "region": "us-east-1",
        "updated_at": "2026-05-15T12:00:00Z",
    }
    team_route = respx_mock.get(f"/teams/{team_id}").mock(
        return_value=Response(200, json=team_data)
    )
    respx_mock.get(
        "/apps/",
        params={"team_id": team_id, "limit": "100", "skip": "20"},
    ).mock(return_value=Response(200, json={"data": [app_data], "count": 1}))

    result = runner.invoke(
        app,
        [
            "apps",
            "list",
            "--team-id",
            team_id,
            "--limit",
            "100",
            "--offset",
            "20",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "apps": [app_data],
            "total_count": 1,
            "limit": 100,
            "offset": 20,
        }
    }
    assert team_route.called
    assert result.stderr == ""


def test_lists_apps_json_returns_missing_required_input_without_team_id(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["apps", "list", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Team ID is required.",
            "hint": "Pass --team-id to choose a team.",
        }
    }
    assert result.stderr == ""


def test_gets_app_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["apps", "get", "00000000-0000-4000-8000-000000000002"],
    )

    assert result.exit_code == 1
    assert "No credentials found." in result.output
    assert "fastapi cloud login" in result.output


@pytest.mark.respx
def test_lists_apps_prompts_for_team_when_team_id_is_missing(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team = {
        "id": "00000000-0000-4000-8000-000000000001",
        "slug": "acme",
        "name": "Acme",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team["id"],
        "slug": "api",
        "name": "API",
        "directory": "backend",
    }
    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [team], "count": 1})
    )
    apps_route = respx_mock.get("/apps/").mock(
        return_value=Response(200, json={"data": [app_data], "count": 1})
    )

    with patch("rich_toolkit.container.getchar") as mock_getchar:
        mock_getchar.side_effect = [Keys.ENTER]
        result = runner.invoke(app, ["apps", "list"])

    assert result.exit_code == 0
    assert "Select the team:" in result.output
    assert "Acme" in result.output
    assert "API" in result.output
    assert apps_route.calls.last.request.url.params["team_id"] == team["id"]


@pytest.mark.respx
def test_lists_apps_returns_missing_required_input_when_no_teams(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(app, ["apps", "list"])

    assert result.exit_code == 1
    assert "No teams found." in result.output
    assert "Create a team before listing apps." in result.output


@pytest.mark.respx
def test_gets_app_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": "00000000-0000-4000-8000-000000000001",
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://api.fastapicloud.app",
    }
    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=app_data)
    )

    result = runner.invoke(app, ["apps", "get", app_data["id"], "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app": {
                **app_data,
                "region": None,
                "updated_at": None,
            }
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_app_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_data = {
        "id": "00000000-0000-4000-8000-000000000001",
        "slug": "strawberry",
        "name": "Strawberry",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_data["id"],
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://api.fastapicloud.app",
    }
    dashboard_url = "https://dashboard.fastapicloud.com/strawberry/apps/api"
    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=app_data)
    )
    respx_mock.get(f"/teams/{team_data['id']}").mock(
        return_value=Response(200, json=team_data)
    )

    result = runner.invoke(app, ["apps", "get", app_data["id"]])

    assert result.exit_code == 0
    assert "📦 API" in result.output
    assert "slug       api" in result.output
    assert "directory  backend" in result.output
    assert "url        https://api.fastapicloud.app" in result.output
    assert f"dashboard  {dashboard_url}" in result.output
    assert f"id         {app_data['id']}" in result.output
    assert f"team id    {app_data['team_id']}" in result.output


@pytest.mark.respx
def test_gets_app_json_returns_not_found_for_unknown_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(404))

    result = runner.invoke(app, ["apps", "get", app_id, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "App not found.",
            "hint": None,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_app_as_json_uses_linked_app_when_id_omitted(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    app_data = {
        "id": configured_app.app_id,
        "team_id": configured_app.team_id,
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://api.fastapicloud.app",
    }
    respx_mock.get(f"/apps/{configured_app.app_id}").mock(
        return_value=Response(200, json=app_data)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["apps", "get", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["app"]["id"] == configured_app.app_id
    assert result.stderr == ""


def test_gets_app_json_returns_missing_required_input_without_app_id(
    logged_in_cli: None,
    tmp_path: Path,
) -> None:
    with changing_dir(tmp_path):
        result = runner.invoke(app, ["apps", "get", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "App ID is required.",
            "hint": "Pass an app ID or run `fastapi cloud apps create --link` first.",
        }
    }
    assert result.stderr == ""


def test_get_app_dashboard_url_uses_settings_team_and_app_slugs() -> None:
    app_data = App.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000002",
            "team_id": "00000000-0000-4000-8000-000000000001",
            "slug": "api",
            "name": "API",
            "directory": "backend",
        }
    )

    assert (
        _get_app_dashboard_url(
            app_data,
            team_slug="strawberry",
            settings=Settings(dashboard_base_url="https://dashboard.example.com"),
        )
        == "https://dashboard.example.com/strawberry/apps/api"
    )


@pytest.mark.respx
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_lists_apps_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    team_data = {
        "id": team_id,
        "slug": "strawberry",
        "name": "Strawberry",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://strawberryrocks.fastapicloud.dev",
        "region": "us-east-1",
        "updated_at": "2026-05-15T12:00:00Z",
    }
    respx_mock.get(f"/teams/{team_id}").mock(return_value=Response(200, json=team_data))
    respx_mock.get("/apps/").mock(
        return_value=Response(200, json={"data": [app_data], "count": 1})
    )

    result = runner.invoke(app, ["apps", "list", "--team-id", team_id])

    assert result.exit_code == 0
    assert "apps" in result.output
    assert "Name  ID" in result.output
    assert "API   00000000-0000-4000-8000-000000000002" in result.output


@pytest.mark.respx
def test_lists_apps_in_human_output_empty(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    team_data = {
        "id": team_id,
        "slug": "strawberry",
        "name": "Strawberry",
    }
    respx_mock.get(f"/teams/{team_id}").mock(return_value=Response(200, json=team_data))
    respx_mock.get(
        "/apps/",
        params={"team_id": team_id, "limit": "100", "skip": "0"},
    ).mock(return_value=Response(200, json={"data": [], "count": 0}))

    result = runner.invoke(app, ["apps", "list", "--team-id", team_id])

    assert result.exit_code == 0
    assert "No apps found." in result.output


def test_lists_apps_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(app, ["apps", "list", "--team-id", "team-1"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output
    assert "fastapi cloud login" in result.output
