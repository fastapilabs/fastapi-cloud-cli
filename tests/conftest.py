import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from typer import rich_utils

from .utils import create_jwt_token


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


@pytest.fixture
def temp_auth_config(tmp_path: Path) -> Generator[Path, None, None]:
    """Provides a temporary auth config setup for testing file operations."""

    with patch(
        "fastapi_cloud_cli.utils.config.get_config_folder", return_value=tmp_path
    ):
        yield tmp_path / "auth.json"
