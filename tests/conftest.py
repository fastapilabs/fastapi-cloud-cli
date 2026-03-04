import os
import sys
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
import respx
from typer import rich_utils

from fastapi_cloud_cli.config import Settings

from .utils import create_jwt_token


@pytest.fixture(autouse=True)
def isolated_config_path() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["FASTAPI_CLOUD_CLI_CONFIG_DIR"] = tmpdir

        yield Path(tmpdir)


@pytest.fixture
def temp_auth_config(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Path, None, None]:
    yield isolated_config_path / "auth.json"


@pytest.fixture(autouse=True)
def reset_syspath() -> Generator[None, None, None]:
    initial_python_path = sys.path.copy()
    try:
        yield
    finally:
        sys.path = initial_python_path


@pytest.fixture(autouse=True, scope="session")
def setup_terminal() -> None:
    rich_utils.MAX_WIDTH = 3000
    rich_utils.FORCE_TERMINAL = False
    return


@pytest.fixture
def settings() -> Settings:
    return Settings.get()


@pytest.fixture
def respx_mock(settings: Settings) -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=settings.base_api_url) as mock_router:
        yield mock_router


@pytest.fixture
def logged_in_cli(temp_auth_config: Path) -> Generator[None, None, None]:
    valid_token = create_jwt_token({"sub": "test_user_12345"})

    temp_auth_config.write_text(f'{{"access_token": "{valid_token}"}}')

    yield


@pytest.fixture
def logged_out_cli(temp_auth_config: Path) -> Generator[None, None, None]:
    assert not temp_auth_config.exists()

    yield


@dataclass
class ConfiguredApp:
    app_id: str
    team_id: str
    path: Path


@pytest.fixture
def configured_app(tmp_path: Path) -> ConfiguredApp:
    app_id = "123"
    team_id = "456"

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    return ConfiguredApp(app_id=app_id, team_id=team_id, path=tmp_path)
