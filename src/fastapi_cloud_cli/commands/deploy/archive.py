import logging
import re
from pathlib import Path, PurePosixPath
from typing import Annotated

import fastar
import rignore
from pydantic import AfterValidator

logger = logging.getLogger(__name__)
import sys
if sys.version_info >= (3, 11):
    import tomllib

def validate_app_directory(v: str | None) -> str | None:
    if v is None:
        return None

    v = v.strip()

    if not v:
        return None

    if v.startswith("~"):
        raise ValueError("cannot start with '~'")

    path = PurePosixPath(v)

    if path.is_absolute():
        raise ValueError("must be a relative path, not absolute")

    if ".." in path.parts:
        raise ValueError("cannot contain '..' path segments")

    normalized = path.as_posix()

    if not re.fullmatch(r"[A-Za-z0-9._/ -]+", normalized):
        raise ValueError(
            "contains invalid characters (allowed: letters, numbers, space, / . _ -)"
        )

    return normalized


AppDirectory = Annotated[str | None, AfterValidator(validate_app_directory)]

def _project_name_from_pyproject(path: Path) -> str:
    if sys.version_info < (3, 11):
        return ""

    if not path.exists():
        return ""

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)

        project_name = data.get("project", {}).get("name")
        if project_name:
            return str(project_name)

        poetry_name = data.get("tool", {}).get("poetry", {}).get("name")
        if poetry_name:
            return str(poetry_name)

    except Exception:
        return ""

    return ""

def _get_app_name(path: Path) -> str:
    pyproject_path = path / "pyproject.toml"
    name = _project_name_from_pyproject(pyproject_path)
    if name:
        return name
    return path.name


def _should_exclude_entry(path: Path) -> bool:
    parts_to_exclude = [
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".git",
        ".gitignore",
        ".fastapicloudignore",
    ]

    if any(part in path.parts for part in parts_to_exclude):
        return True

    if path.suffix == ".pyc":
        return True

    if path.name == ".env" or path.name.startswith(".env."):
        return True

    return False


def _rignore_walk(path: Path) -> rignore.Walker:
    return rignore.walk(
        path,
        should_exclude_entry=_should_exclude_entry,
        additional_ignore_paths=[".fastapicloudignore"],
        ignore_hidden=False,
    )


def archive(path: Path, tar_path: Path) -> Path:
    logger.debug("Starting archive creation for path: %s", path)
    files = _rignore_walk(path)

    logger.debug("Archive will be created at: %s", tar_path)

    file_count = 0
    with fastar.open(tar_path, "w:zst", sparse=False) as tar:
        for filename in files:
            if filename.is_dir():
                continue

            arcname = filename.relative_to(path)
            logger.debug("Adding %s to archive", arcname)
            tar.append(filename, arcname=arcname)
            file_count += 1

    logger.debug("Archive created successfully with %s files", file_count)
    return tar_path


def _get_large_files(path: Path, threshold_mb: int) -> list[tuple[Path, int]]:
    threshold_bytes = threshold_mb * 1024 * 1024
    large_files = []
    files = _rignore_walk(path)
    for filename in files:
        if filename.is_dir():
            continue
        file_size = filename.stat().st_size
        if file_size > threshold_bytes:
            large_files.append((filename.relative_to(path), file_size))

    return sorted(large_files, key=lambda x: x[1], reverse=True)
