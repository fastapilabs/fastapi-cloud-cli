from pathlib import Path

from fastapi_cloud_cli.config import Settings


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
