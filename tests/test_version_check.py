import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import httpx
import pytest
import respx
import time_machine
from click.testing import CliRunner

from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.config import get_version_check_cache_path
from fastapi_cloud_cli.utils.version_check import (
    PYPI_JSON_URL,
    BackgroundVersionCheck,
    VersionUpdate,
    check_for_update,
    format_update_message,
    get_upgrade_command,
    is_newer_version,
    read_cached_latest_version,
    write_latest_version_cache,
)


@pytest.fixture
def current_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fastapi_cloud_cli.utils.version_check.__version__", "0.17.1")


def test_is_newer_version() -> None:
    assert is_newer_version("0.18.0", "0.17.1")
    assert not is_newer_version("0.17.1", "0.17.1")
    assert not is_newer_version("0.17.0", "0.17.1")
    assert not is_newer_version("0.18.0rc1", "0.17.1")
    assert not is_newer_version("0.17.1.post1", "0.17.1")
    assert not is_newer_version("not-a-version", "0.17.1")


@respx.mock
def test_check_for_update_returns_update_when_pypi_has_newer_version(
    current_version: None,
) -> None:
    route = respx.get(PYPI_JSON_URL).mock(
        return_value=httpx.Response(200, json={"info": {"version": "0.18.0"}})
    )

    update = check_for_update()

    assert route.called
    assert update == VersionUpdate(current="0.17.1", latest="0.18.0")


@respx.mock
@time_machine.travel(
    datetime(2026, 5, 20, 12, 5, tzinfo=timezone.utc),
    tick=False,
)
def test_check_for_update_uses_fresh_cache_without_network(
    current_version: None,
) -> None:
    cache_path = get_version_check_cache_path()
    cache_path.write_text(
        json.dumps(
            {
                "latest_version": "0.18.0",
                "checked_at": "2026-05-20T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    update = check_for_update()

    assert update == VersionUpdate(current="0.17.1", latest="0.18.0")


@respx.mock
@time_machine.travel(
    datetime(2026, 5, 20, 12, 5, tzinfo=timezone.utc),
    tick=False,
)
def test_check_for_update_refreshes_stale_cache(
    current_version: None,
) -> None:
    cache_path = get_version_check_cache_path()
    cache_path.write_text(
        json.dumps(
            {
                "latest_version": "0.18.0",
                "checked_at": "2026-05-18T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    respx.get(PYPI_JSON_URL).mock(
        return_value=httpx.Response(200, json={"info": {"version": "0.19.0"}})
    )

    update = check_for_update()

    assert update == VersionUpdate(current="0.17.1", latest="0.19.0")
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {
        "latest_version": "0.19.0",
        "checked_at": "2026-05-20T12:05:00+00:00",
    }


@respx.mock
def test_check_for_update_returns_none_when_current_is_latest(
    current_version: None,
) -> None:
    respx.get(PYPI_JSON_URL).mock(
        return_value=httpx.Response(200, json={"info": {"version": "0.17.1"}})
    )

    update = check_for_update()

    assert update is None


@respx.mock
def test_check_for_update_ignores_network_errors(current_version: None) -> None:
    respx.get(PYPI_JSON_URL).mock(side_effect=httpx.ConnectError("offline"))

    update = check_for_update()

    assert update is None


@respx.mock
def test_check_for_update_ignores_invalid_payload(current_version: None) -> None:
    respx.get(PYPI_JSON_URL).mock(
        return_value=httpx.Response(200, json={"info": {"version": None}})
    )

    update = check_for_update()

    assert update is None


@time_machine.travel(
    datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
    tick=False,
)
def test_read_cached_latest_version_ignores_stale_cache(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "version-check.json"
    cache_path.write_text(
        json.dumps(
            {
                "latest_version": "0.18.0",
                "checked_at": "2026-05-18T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    latest_version = read_cached_latest_version(
        cache_path,
        ttl=timedelta(hours=24),
    )

    assert latest_version is None


def test_read_cached_latest_version_ignores_invalid_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "version-check.json"
    cache_path.write_text("not-json", encoding="utf-8")

    latest_version = read_cached_latest_version(
        cache_path,
    )

    assert latest_version is None


def test_read_cached_latest_version_ignores_non_simple_version(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "version-check.json"
    cache_path.write_text(
        json.dumps(
            {
                "latest_version": "0.18.0rc1",
                "checked_at": "2026-05-20T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    latest_version = read_cached_latest_version(
        cache_path,
    )

    assert latest_version is None


def test_write_latest_version_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "version-check.json"

    write_latest_version_cache(
        cache_path,
        latest_version="0.18.0",
        now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
    )

    assert json.loads(cache_path.read_text(encoding="utf-8")) == {
        "latest_version": "0.18.0",
        "checked_at": "2026-05-20T12:00:00+00:00",
    }


def test_write_latest_version_cache_ignores_write_errors(tmp_path: Path) -> None:
    blocking_path = tmp_path / "not-a-directory"
    blocking_path.write_text("", encoding="utf-8")

    write_latest_version_cache(
        blocking_path / "version-check.json",
        latest_version="0.18.0",
        now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
    )

    assert blocking_path.is_file()


def test_get_upgrade_command_uses_detected_installer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_detect_installer(package_name: str) -> Any:
        assert package_name == "fastapi-cloud-cli"
        return SimpleNamespace(upgrade_cmd="uv tool upgrade fastapi-cloud-cli")

    monkeypatch.setattr(
        "fastapi_cloud_cli.utils.version_check.detect_installer",
        fake_detect_installer,
    )

    assert get_upgrade_command() == "uv tool upgrade fastapi-cloud-cli"


def test_get_upgrade_command_falls_back_when_installer_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "fastapi_cloud_cli.utils.version_check.detect_installer",
        lambda package_name: None,
    )

    assert get_upgrade_command() == "pip install --upgrade fastapi-cloud-cli"


def test_get_upgrade_command_propagates_detector_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_detector(package_name: str) -> None:
        raise RuntimeError(f"Could not inspect {package_name}")

    monkeypatch.setattr(
        "fastapi_cloud_cli.utils.version_check.detect_installer",
        broken_detector,
    )

    with pytest.raises(RuntimeError, match="Could not inspect fastapi-cloud-cli"):
        get_upgrade_command()


def test_format_update_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fastapi_cloud_cli.utils.version_check.get_upgrade_command",
        lambda: "uv tool upgrade fastapi-cloud-cli",
    )

    message = format_update_message(VersionUpdate(current="0.17.1", latest="0.18.0"))

    assert not message.startswith("\n")
    assert "→ [bold]0.18.0[/]" in message
    assert '\n\nRun "[blue]uv tool upgrade fastapi-cloud-cli[/]" to upgrade.' in message
    assert "https://pypi.org/project/fastapi-cloud-cli/" not in message


def _seed_fresh_update_cache(latest_version: str = "999.0.0") -> None:
    write_latest_version_cache(
        get_version_check_cache_path(),
        latest_version=latest_version,
        now=datetime.now(timezone.utc),
    )


def test_get_rich_toolkit_prints_update_after_toolkit_output() -> None:
    @click.command()
    def command_with_toolkit() -> None:
        with get_rich_toolkit() as toolkit:
            toolkit.print("command output")

    _seed_fresh_update_cache()
    result = CliRunner().invoke(
        command_with_toolkit,
        [],
        env={"FASTAPI_CLOUD_DISABLE_VERSION_CHECK": ""},
    )

    assert result.exit_code == 0, result.output
    assert "command output" in result.output
    assert result.output.count("A newer FastAPI Cloud CLI version is available") == 1
    assert result.output.rfind("command output") < result.output.rfind("A newer")


def test_get_rich_toolkit_skips_update_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FASTAPI_CLOUD_DISABLE_VERSION_CHECK", "1")
    _seed_fresh_update_cache()

    with get_rich_toolkit() as toolkit:
        toolkit.print("command output")

    output = capsys.readouterr().out
    assert "command output" in output
    assert "A newer FastAPI Cloud CLI version is available" not in output


def test_background_check_stores_result_and_returns_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "fastapi_cloud_cli.utils.version_check.check_for_update",
        lambda: VersionUpdate(current="0.17.1", latest="0.18.0"),
    )
    check = BackgroundVersionCheck()

    check.start()
    message = check.get_update_message()

    assert message is not None
    assert "A newer FastAPI Cloud CLI version is available" in message
    assert "→ [bold]0.18.0[/]" in message
    assert check.get_update_message() is None


def test_background_check_returns_no_message_without_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "fastapi_cloud_cli.utils.version_check.check_for_update",
        lambda: None,
    )
    check = BackgroundVersionCheck()

    check.start()
    message = check.get_update_message()

    assert message is None


def test_background_check_hides_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
    recwarn: pytest.WarningsRecorder,
) -> None:
    def broken_check() -> None:
        raise RuntimeError("version check failed unexpectedly")

    monkeypatch.setattr(
        "fastapi_cloud_cli.utils.version_check.check_for_update",
        broken_check,
    )
    check = BackgroundVersionCheck()

    check.start()

    assert check.get_update_message() is None
    assert not any(
        warning.category is pytest.PytestUnhandledThreadExceptionWarning
        for warning in recwarn
    )
