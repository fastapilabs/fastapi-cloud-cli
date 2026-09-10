import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.cli import cloud_app as app
from tests.utils import Keys, SnapshotCliRunner, changing_dir

runner = SnapshotCliRunner()

assets_path = Path(__file__).parent / "assets"


@pytest.mark.respx
@pytest.mark.parametrize("is_secret", [False, True])
def test_updates_existing_variable_using_returned_secret_status(
    logged_in_cli: None, respx_mock: respx.MockRouter, is_secret: bool
) -> None:
    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"TOKEN": {"value": "updated", "is_secret": not is_secret}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "ANOTHER_VAR",
                        "value": "unchanged",
                        "is_secret": not is_secret,
                    },
                    {
                        "name": "TOKEN",
                        "is_secret": is_secret,
                        "value": None if is_secret else "updated",
                    },
                ],
                "count": 2,
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "TOKEN",
            "updated",
            "--app-id",
            "123",
            "--json",
            *([] if is_secret else ["--secret"]),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"app_id": "123", "name": "TOKEN", "is_secret": is_secret}
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_updating_existing_secret_shows_secret_output(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"TOKEN": {"value": "updated", "is_secret": False}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200, json={"data": [{"name": "TOKEN", "is_secret": True}], "count": 1}
        )
    )

    result = runner.invoke(app, ["env", "set", "TOKEN", "updated", "--app-id", "123"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Secret environment variable TOKEN set.\
""")


@pytest.mark.respx
def test_set_json_reports_managed_variable_error(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    message = (
        "Cannot modify integration-managed environment variables: 'DATABASE_URL'. "
        "Disconnect the associated integration resources to remove these variables."
    )
    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"DATABASE_URL": {"value": "postgres://db", "is_secret": True}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(return_value=Response(400, json={"detail": message}))

    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "DATABASE_URL",
            "postgres://db",
            "--secret",
            "--app-id",
            "123",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {"code": "invalid_input", "message": message, "hint": None}
    }
    assert result.stderr == ""


@pytest.fixture
def configured_app(tmp_path: Path) -> Path:
    app_id = "123"
    team_id = "456"

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    return tmp_path


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


def test_shows_a_message_if_app_is_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 1
    assert "App ID is required." in result.output


@pytest.mark.respx
def test_shows_a_message_if_something_is_wrong(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"SOME_VAR": {"value": "secret", "is_secret": False}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(return_value=Response(500))

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret"])

    assert result.exit_code == 1
    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )


@pytest.mark.respx
def test_shows_message_when_it_sets(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"SOME_VAR": {"value": "secret", "is_secret": False}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [{"name": "SOME_VAR", "value": "secret", "is_secret": False}],
                "count": 1,
            },
        )
    )

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Environment variable SOME_VAR set.\
""")


@pytest.mark.respx
def test_asks_for_name_and_value(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    steps = [*"API", Keys.ENTER, *"secret", Keys.ENTER]

    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"API": {"value": "secret", "is_secret": False}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [{"name": "API", "value": "secret", "is_secret": False}],
                "count": 1,
            },
        )
    )

    with (
        changing_dir(configured_app),
        patch("rich_toolkit.container.getchar", side_effect=steps),
    ):
        result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Enter the name of the environment variable to set:


Enter the name of the environment variable to set:
A

Enter the name of the environment variable to set:
AP

Enter the name of the environment variable to set:
API

Enter the name of the environment variable to set: API
Enter the value of the environment variable:


Enter the value of the environment variable:
s

Enter the value of the environment variable:
se

Enter the value of the environment variable:
sec

Enter the value of the environment variable:
secr

Enter the value of the environment variable:
secre

Enter the value of the environment variable:
secret

Enter the value of the environment variable: secret

Environment variable API set.\
""")


@pytest.mark.respx
def test_asks_for_name_and_value_for_secret(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    steps = [*"API", Keys.ENTER, *"secret", Keys.ENTER]

    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"API": {"value": "secret", "is_secret": True}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [{"name": "API", "value": None, "is_secret": True}],
                "count": 1,
            },
        )
    )

    with (
        changing_dir(configured_app),
        patch("rich_toolkit.container.getchar", side_effect=steps),
    ):
        result = runner.invoke(app, ["env", "set", "--secret"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Enter the name of the secret to set:


Enter the name of the secret to set:
A

Enter the name of the secret to set:
AP

Enter the name of the secret to set:
API

Enter the name of the secret to set: API
Enter the secret value:


Enter the secret value:
*

Enter the secret value:
**

Enter the secret value:
***

Enter the secret value:
****

Enter the secret value:
*****

Enter the secret value:
******

Enter the secret value: ******

Secret environment variable API set.\
""")


@pytest.mark.respx
def test_sets_secret_flag(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.put(
        "/apps/123/environment-variables/",
        json={
            "upsert": {"SOME_VAR": {"value": "secret", "is_secret": True}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [{"name": "SOME_VAR", "value": None, "is_secret": True}],
                "count": 1,
            },
        )
    )

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret", "--secret"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Secret environment variable SOME_VAR set.\
""")


@pytest.mark.respx
@pytest.mark.parametrize("no_redeploy", [False, True])
def test_sets_environment_variable_as_json(
    logged_in_cli: None, respx_mock: respx.MockRouter, no_redeploy: bool
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.put(
        f"/apps/{app_id}/environment-variables/",
        json={
            "upsert": {"LOG_LEVEL": {"value": "info", "is_secret": False}},
            "delete": [],
            "redeploy": not no_redeploy,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [{"name": "LOG_LEVEL", "value": "info", "is_secret": False}],
                "count": 1,
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "LOG_LEVEL",
            "info",
            "--app-id",
            app_id,
            "--json",
            *(["--no-redeploy"] if no_redeploy else []),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "name": "LOG_LEVEL",
            "is_secret": False,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_sets_secret_environment_variable_as_json(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.put(
        f"/apps/{app_id}/environment-variables/",
        json={
            "upsert": {"DATABASE_URL": {"value": "postgres://db", "is_secret": True}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [{"name": "DATABASE_URL", "value": None, "is_secret": True}],
                "count": 1,
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "DATABASE_URL",
            "postgres://db",
            "--secret",
            "--app-id",
            app_id,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "name": "DATABASE_URL",
            "is_secret": True,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_sets_environment_variable_as_json_reads_value_stdin(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.put(
        f"/apps/{app_id}/environment-variables/",
        json={
            "upsert": {"DATABASE_URL": {"value": "postgres://db", "is_secret": True}},
            "delete": [],
            "redeploy": True,
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "data": [{"name": "DATABASE_URL", "value": None, "is_secret": True}],
                "count": 1,
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "DATABASE_URL",
            "--value-stdin",
            "--secret",
            "--app-id",
            app_id,
            "--json",
        ],
        input="postgres://db\n",
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "name": "DATABASE_URL",
            "is_secret": True,
        }
    }
    assert result.stderr == ""


def test_set_json_returns_missing_required_input_without_name(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["env", "set", "--app-id", "00000000-0000-4000-8000-000000000002", "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Environment variable name is required.",
            "hint": "Pass NAME to choose an environment variable.",
        }
    }
    assert result.stderr == ""


def test_set_rejects_value_and_value_stdin(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "LOG_LEVEL",
            "info",
            "--value-stdin",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--json",
        ],
        input="debug\n",
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "Only one environment variable value source can be used.",
            "hint": "Pass either VALUE or --value-stdin.",
        }
    }
    assert result.stderr == ""


def test_set_json_returns_missing_required_input_without_value(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "LOG_LEVEL",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Environment variable value is required.",
            "hint": "Pass VALUE or --value-stdin to set the environment variable.",
        }
    }
    assert result.stderr == ""
