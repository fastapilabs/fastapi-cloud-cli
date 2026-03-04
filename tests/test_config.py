from pathlib import Path

import pytest
import typer

from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.config import get_config_folder


def test_loads_default_values_when_file_does_not_exist() -> None:
    default_settings = Settings()

    settings = Settings.from_user_settings(Path("non_existent_file.json"))

    assert settings.base_api_url == default_settings.base_api_url
    assert settings.client_id == default_settings.client_id


def test_loads_settings_even_when_file_is_broken(tmp_path: Path) -> None:
    broken_settings_path = tmp_path / "broken_settings.json"
    broken_settings_path.write_text("this is not json")

    default_settings = Settings()

    settings = Settings.from_user_settings(broken_settings_path)

    assert settings.base_api_url == default_settings.base_api_url
    assert settings.client_id == default_settings.client_id


def test_loads_partial_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"base_api_url": "https://example.com"}')

    default_settings = Settings()

    settings = Settings.from_user_settings(settings_path)

    assert settings.base_api_url == "https://example.com"
    assert settings.client_id == default_settings.client_id


def test_get_config_folder_reads_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FASTAPI_CLOUD_CLI_CONFIG_DIR", str(tmp_path))

    assert get_config_folder() == tmp_path


def test_get_config_folder_defaults_to_app_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FASTAPI_CLOUD_CLI_CONFIG_DIR", raising=False)

    assert get_config_folder() == Path(typer.get_app_dir("fastapi-cli"))
