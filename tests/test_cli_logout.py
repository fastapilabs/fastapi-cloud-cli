from pathlib import Path

from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app

runner = CliRunner()


def test_logout_with_existing_auth_file(temp_auth_config: Path) -> None:
    temp_auth_config.write_text('{"access_token": "test_token"}')

    assert temp_auth_config.exists()

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert "You are now logged out! 🚀" in result.output

    assert not temp_auth_config.exists()


def test_logout_with_no_auth_file(temp_auth_config: Path) -> None:
    assert not temp_auth_config.exists()

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert "You are now logged out! 🚀" in result.output

    assert not temp_auth_config.exists()
