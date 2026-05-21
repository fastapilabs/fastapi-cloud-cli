import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from detect_installer import InstallerInfo, detect_installer

from fastapi_cloud_cli import __version__
from fastapi_cloud_cli.utils.config import get_config_folder

logger = logging.getLogger(__name__)

PACKAGE_NAME = "fastapi-cloud-cli"
DEFAULT_UPGRADE_COMMAND = f"pip install --upgrade {PACKAGE_NAME}"
PYPI_JSON_URL = "https://pypi.org/pypi/fastapi-cloud-cli/json"
VERSION_CHECK_TIMEOUT_SECONDS = 2.0
VERSION_CHECK_JOIN_TIMEOUT_SECONDS = 0.2
VERSION_CHECK_CACHE_TTL = timedelta(hours=24)
DISABLE_VERSION_CHECK_ENV = "FASTAPI_CLOUD_DISABLE_VERSION_CHECK"
VERSION_CHECK_CACHE_FILENAME = "version-check.json"
SIMPLE_RELEASE_VERSION_RE = re.compile(r"\d+(?:\.\d+)*")


@dataclass(frozen=True)
class VersionUpdate:
    current: str
    latest: str


def get_version_check_cache_path() -> Path:
    return get_config_folder() / VERSION_CHECK_CACHE_FILENAME


def _parse_simple_release_version(version: str) -> tuple[int, ...] | None:
    if not SIMPLE_RELEASE_VERSION_RE.fullmatch(version):
        logger.debug("Skipping non-simple version string: %r", version)
        return None

    return tuple(int(part) for part in version.split("."))


def is_newer_version(latest: str, current: str) -> bool:
    latest_parts = _parse_simple_release_version(latest)
    current_parts = _parse_simple_release_version(current)

    if latest_parts is None or current_parts is None:
        return False

    version_length = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (version_length - len(latest_parts))
    current_parts += (0,) * (version_length - len(current_parts))

    return latest_parts > current_parts


def read_cached_latest_version(
    cache_path: Path,
    *,
    now: datetime | None = None,
    ttl: timedelta = VERSION_CHECK_CACHE_TTL,
) -> str | None:
    now = now or datetime.now(timezone.utc)

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.debug("Could not read CLI version cache: %s", error)
        return None

    if not isinstance(data, dict):
        return None

    latest_version = data.get("latest_version")
    checked_at_value = data.get("checked_at")

    if not isinstance(latest_version, str) or not isinstance(checked_at_value, str):
        return None

    if _parse_simple_release_version(latest_version) is None:
        return None

    try:
        checked_at = datetime.fromisoformat(checked_at_value)
    except ValueError:
        return None

    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)

    if now - checked_at > ttl:
        return None

    return latest_version


def write_latest_version_cache(
    cache_path: Path,
    *,
    latest_version: str,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    data = {
        "latest_version": latest_version,
        "checked_at": now.isoformat(),
    }

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
    except OSError as error:
        logger.debug("Could not write CLI version cache: %s", error)


def fetch_latest_version(
    *,
    current_version: str = __version__,
) -> str | None:
    headers = {"User-Agent": f"fastapi-cloud-cli/{current_version}"}

    try:
        with httpx.Client(
            timeout=httpx.Timeout(VERSION_CHECK_TIMEOUT_SECONDS),
            headers=headers,
        ) as client:
            response = client.get(PYPI_JSON_URL)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        logger.debug("Could not check latest CLI version: %s", error)
        return None

    info = data.get("info") if isinstance(data, dict) else None
    version = info.get("version") if isinstance(info, dict) else None

    if not isinstance(version, str):
        logger.debug("PyPI version payload did not contain an info.version string")
        return None

    return version


def check_for_update(
    *,
    current_version: str = __version__,
    cache_path: Path | None = None,
    now: datetime | None = None,
) -> VersionUpdate | None:
    now = now or datetime.now(timezone.utc)
    cache_path = cache_path or get_version_check_cache_path()

    latest_version = read_cached_latest_version(cache_path, now=now)
    if latest_version is None:
        latest_version = fetch_latest_version(current_version=current_version)
        if latest_version is None:
            return None

        write_latest_version_cache(
            cache_path,
            latest_version=latest_version,
            now=now,
        )

    if not is_newer_version(latest_version, current_version):
        return None

    return VersionUpdate(current=current_version, latest=latest_version)


def get_upgrade_command(
    *,
    detector: Callable[[str], InstallerInfo | None] = detect_installer,
) -> str:
    try:
        installer_info = detector(PACKAGE_NAME)
    except Exception as error:
        logger.debug("Could not detect CLI installer: %s", error)
        return DEFAULT_UPGRADE_COMMAND

    if installer_info is None or installer_info.upgrade_cmd is None:
        return DEFAULT_UPGRADE_COMMAND

    return installer_info.upgrade_cmd


def format_update_message(
    update: VersionUpdate,
    *,
    upgrade_command: str | None = None,
) -> str:
    upgrade_command = upgrade_command or get_upgrade_command()

    return (
        "A newer FastAPI Cloud CLI version is available: "
        f"{update.current} → [bold]{update.latest}[/]\n\n"
        f'Run "[blue]{upgrade_command}[/]" to upgrade.'
    )


class BackgroundVersionCheck:
    def __init__(
        self,
        *,
        check_for_update: Callable[[], VersionUpdate | None] = check_for_update,
        join_timeout: float = VERSION_CHECK_JOIN_TIMEOUT_SECONDS,
    ) -> None:
        self._check_for_update = check_for_update
        self._join_timeout = join_timeout
        self._thread: threading.Thread | None = None
        self._update: VersionUpdate | None = None
        self._message_returned = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self._update = self._check_for_update()
        except Exception as error:
            logger.debug("Could not check latest CLI version: %s", error)

    def suppress(self) -> None:
        self._message_returned = True

    def get_update_message(self) -> str | None:
        if self._message_returned:
            return None

        if self._thread:
            self._thread.join(timeout=self._join_timeout)

        if self._update:
            self._message_returned = True
            return format_update_message(self._update)

        return None
