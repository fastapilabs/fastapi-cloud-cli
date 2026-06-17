import json
from pathlib import Path

from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app

runner = CliRunner()


def test_apps_unlink_removes_cloud_json_and_preserves_fastapicloud_dir(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / ".fastapicloud"
    config_dir.mkdir(parents=True)

    cloud_json = config_dir / "cloud.json"
    cloud_json.write_text('{"app_id": "123", "team_id": "456"}')

    readme_file = config_dir / "README.md"
    readme_file.write_text("# FastAPI Cloud Configuration")

    gitignore_file = config_dir / ".gitignore"
    gitignore_file.write_text("*")

    result = runner.invoke(app, ["apps", "unlink", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "Removed app link" in result.output
    assert "Deleted" in result.output
    assert config_dir.exists()
    assert not cloud_json.exists()
    assert readme_file.exists()
    assert gitignore_file.exists()


def test_unlink_compatibility_shortcut_removes_cloud_json(tmp_path: Path) -> None:
    config_dir = tmp_path / ".fastapicloud"
    config_dir.mkdir(parents=True)

    cloud_json = config_dir / "cloud.json"
    cloud_json.write_text('{"app_id": "123", "team_id": "456"}')

    readme_file = config_dir / "README.md"
    readme_file.write_text("# FastAPI Cloud Configuration")

    result = runner.invoke(app, ["unlink", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "Removed app link" in result.output
    assert not cloud_json.exists()
    assert readme_file.exists()
    assert config_dir.exists()


def test_apps_unlink_as_json(tmp_path: Path) -> None:
    config_dir = tmp_path / ".fastapicloud"
    config_dir.mkdir(parents=True)

    cloud_json = config_dir / "cloud.json"
    cloud_json.write_text('{"app_id": "123", "team_id": "456"}')

    result = runner.invoke(app, ["apps", "unlink", "--path", str(tmp_path), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "unlinked": True,
            "removed_path": str(cloud_json),
        }
    }
    assert result.stderr == ""
    assert config_dir.exists()
    assert not cloud_json.exists()


def test_unlink_compatibility_shortcut_as_json(tmp_path: Path) -> None:
    config_dir = tmp_path / ".fastapicloud"
    config_dir.mkdir(parents=True)

    cloud_json = config_dir / "cloud.json"
    cloud_json.write_text('{"app_id": "123", "team_id": "456"}')

    readme_file = config_dir / "README.md"
    readme_file.write_text("# FastAPI Cloud Configuration")

    result = runner.invoke(app, ["unlink", "--path", str(tmp_path), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "unlinked": True,
            "removed_path": str(cloud_json),
        }
    }
    assert result.stderr == ""
    assert config_dir.exists()
    assert not cloud_json.exists()
    assert readme_file.exists()


def test_apps_unlink_json_returns_not_linked_when_config_is_missing(
    tmp_path: Path,
) -> None:
    result = runner.invoke(app, ["apps", "unlink", "--path", str(tmp_path), "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_linked",
            "message": "No app is linked to this directory.",
            "hint": "Run `fastapi cloud link` to link an app.",
        }
    }
    assert result.stderr == ""


def test_unlink_when_no_configuration_exists(tmp_path: Path) -> None:
    result = runner.invoke(app, ["unlink", "--path", str(tmp_path)])

    assert result.exit_code == 1
    assert "No app is linked to this directory." in result.output
