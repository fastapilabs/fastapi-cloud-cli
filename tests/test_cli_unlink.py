from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app

runner = CliRunner()


def test_unlink_removes_fastapicloud_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / ".fastapicloud"
    config_dir.mkdir(parents=True)

    cloud_json = config_dir / "cloud.json"
    cloud_json.write_text('{"app_id": "123", "team_id": "456"}')

    readme_file = config_dir / "README.md"
    readme_file.write_text("# FastAPI Cloud Configuration")

    gitignore_file = config_dir / ".gitignore"
    gitignore_file.write_text("*")

    with patch("fastapi_cloud_cli.commands.unlink.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["unlink"])

    assert result.exit_code == 0
    assert (
        "FastAPI Cloud configuration has been unlinked successfully! 🚀"
        in result.output
    )

    assert not config_dir.exists()
    assert not cloud_json.exists()
    assert not readme_file.exists()
    assert not gitignore_file.exists()


def test_unlink_when_no_configuration_exists(tmp_path: Path) -> None:
    config_dir = tmp_path / ".fastapicloud"
    assert not config_dir.exists()

    with patch("fastapi_cloud_cli.commands.unlink.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["unlink"])

    assert result.exit_code == 1
    assert (
        "No FastAPI Cloud configuration found in the current directory."
        in result.output
    )
