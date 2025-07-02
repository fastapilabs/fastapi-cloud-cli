import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from typer import rich_utils


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
def logged_in_cli() -> Generator[None, None, None]:
    with patch("fastapi_cloud_cli.utils.auth.get_auth_token", return_value=True):
        yield


@pytest.fixture
def logged_out_cli() -> Generator[None, None, None]:
    with patch("fastapi_cloud_cli.utils.auth.get_auth_token", return_value=None):
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
