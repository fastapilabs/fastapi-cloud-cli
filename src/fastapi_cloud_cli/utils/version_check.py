import json
import logging
import re
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from detect_installer import detect_installer
from pydantic import AwareDatetime, BaseModel, ValidationError

from fastapi_cloud_cli import __version__
from fastapi_cloud_cli.utils.config import get_version_check_cache_path

logger = logging.getLogger(__name__)

PACKAGE_NAME = "fastapi-cloud-cli"
DEFAULT_UPGRADE_COMMAND = f"pip install --upgrade {PACKAGE_NAME}"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
VERSION_CHECK_TIMEOUT_SECONDS = 2.0
VERSION_CHECK_JOIN_TIMEOUT_SECONDS = 0.2
VERSION_CHECK_CACHE_TTL = timedelta(hours=24)
DISABLE_VERSION_CHECK_ENV = "FASTAPI_CLOUD_DISABLE_VERSION_CHECK"
SIMPLE_RELEASE_VERSION_RE = re.compile(r"\d+(?:\.\d+)*")


@dataclass(frozen=True)
class VersionUpdate:
    current: str
    latest: str


class VersionCheckCache(BaseModel):
    latest_version: str
    checked_at: AwareDatetime


class PyPIProjectInfo(BaseModel):
    version: str


class PyPIProjectResponse(BaseModel):
    info: PyPIProjectInfo


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

    return latest_parts > current_parts


def read_cached_latest_version(
    cache_path: Path,
    *,
    ttl: timedelta = VERSION_CHECK_CACHE_TTL,
) -> str | None:
    now = datetime.now(timezone.utc)

    try:
        cache = VersionCheckCache.model_validate_json(
            cache_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        logger.debug("Could not read CLI version cache: %s", error)
        return None

    if _parse_simple_release_version(cache.latest_version) is None:
        return None

    if now - cache.checked_at > ttl:
        return None

    return cache.latest_version


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


def fetch_latest_version() -> str | None:
    headers = {"User-Agent": f"fastapi-cloud-cli/{__version__}"}

    try:
        with httpx.Client(
            timeout=httpx.Timeout(VERSION_CHECK_TIMEOUT_SECONDS),
            headers=headers,
        ) as client:
            response = client.get(PYPI_JSON_URL)
            response.raise_for_status()
            data = PyPIProjectResponse.model_validate_json(response.text)
    except (httpx.HTTPError, ValidationError) as error:
        logger.debug("Could not check latest CLI version: %s", error)
        return None

    return data.info.version


def check_for_update() -> VersionUpdate | None:
    cache_path = get_version_check_cache_path()

    if (latest_version := read_cached_latest_version(cache_path)) is None:
        if (latest_version := fetch_latest_version()) is None:
            return None

        write_latest_version_cache(
            cache_path,
            latest_version=latest_version,
        )

    if not is_newer_version(latest_version, __version__):
        return None

    return VersionUpdate(current=__version__, latest=latest_version)


def get_upgrade_command() -> str:
    installer_info = detect_installer(PACKAGE_NAME)

    if installer_info is None or installer_info.upgrade_cmd is None:
        return DEFAULT_UPGRADE_COMMAND

    return installer_info.upgrade_cmd


def format_update_message(
    update: VersionUpdate,
) -> str:
    return (
        "A newer FastAPI Cloud CLI version is available: "
        f"{update.current} → [bold]{update.latest}[/]\n\n"
        f'Run "[blue]{get_upgrade_command()}[/]" to upgrade.'
    )


class BackgroundVersionCheck:
    def __init__(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._update: VersionUpdate | None = None
        self._message_returned = False

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        with suppress(Exception):
            self._update = check_for_update()

    def get_update_message(self) -> str | None:
        if self._message_returned:
            return None

        self._thread.join(timeout=VERSION_CHECK_JOIN_TIMEOUT_SECONDS)

        if self._update:
            self._message_returned = True
            return format_update_message(self._update)

        return None
