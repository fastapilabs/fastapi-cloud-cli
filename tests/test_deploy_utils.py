from pathlib import Path

import pytest

from fastapi_cloud_cli.commands.deploy import (
    _get_large_files,
    _should_exclude_entry,
    validate_app_directory,
)
from fastapi_cloud_cli.utils.api import DeploymentStatus


def _create_file(path: Path, size_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        if size_bytes > 0:
            f.seek(size_bytes - 1)
            f.write(b"\0")


@pytest.mark.parametrize(
    "path",
    [
        Path("/project/.venv/lib/python3.11/site-packages/some_package"),
        Path("/project/src/__pycache__/module.cpython-311.pyc"),
        Path("/project/.mypy_cache/3.11/module.meta.json"),
        Path("/project/.pytest_cache/v/cache/lastfailed"),
        Path("/project/src/module.pyc"),
        Path("/project/src/subdir/another/module.pyc"),
        Path("/project/subproject/.venv/lib/python3.11/site-packages"),
        Path("/project/.venv/lib/__pycache__/module.pyc"),
        Path(".venv"),
        Path("__pycache__"),
        Path("module.pyc"),
        Path("/project/.env"),
        Path("/project/.env.local"),
        Path("/project/.env.production"),
        Path(".env"),
        Path(".env.development"),
    ],
)
def test_excludes_paths(path: Path) -> None:
    """Should exclude paths that match exclusion criteria."""
    assert _should_exclude_entry(path) is True


@pytest.mark.parametrize(
    "path",
    [
        Path("/project/src/module.py"),
        Path("/project/src/utils"),
        Path("/project/src/my_cache_utils.py"),
        Path("/project/venv/lib/python3.11/site-packages"),  # no leading dot
        Path("/project/pycache/some_file.py"),  # no underscores
        Path("/project/src/module.pyx"),  # similar to .pyc but different
        Path("/project/config.json"),
        Path("/project/README.md"),
        Path("/project/.envrc"),  # not a .env file
        Path("/project/env.py"),  # not a .env file
    ],
)
def test_includes_paths(path: Path) -> None:
    """Should not exclude paths that don't match exclusion criteria."""
    assert _should_exclude_entry(path) is False


@pytest.mark.parametrize(
    "status,expected",
    [
        (DeploymentStatus.waiting_upload, "Awaiting Upload"),
        (DeploymentStatus.ready_for_build, "Build Queued"),
        (DeploymentStatus.building, "Building"),
        (DeploymentStatus.extracting, "Extracting Upload"),
        (DeploymentStatus.extracting_failed, "Extraction Failed"),
        (DeploymentStatus.building_image, "Building Image"),
        (DeploymentStatus.building_image_failed, "Build Failed"),
        (DeploymentStatus.deploying, "Deploying Image"),
        (DeploymentStatus.deploying_failed, "Deployment Failed"),
        (DeploymentStatus.verifying, "Verifying Readiness"),
        (DeploymentStatus.verifying_failed, "Verification Failed"),
        (DeploymentStatus.verifying_skipped, "Verification Skipped"),
        (DeploymentStatus.success, "Ready"),
        (DeploymentStatus.expired, "Expired"),
        (DeploymentStatus.failed, "Failed"),
    ],
)
def test_deployment_status_to_human_readable(
    status: DeploymentStatus, expected: str
) -> None:
    """Should convert deployment status to human readable format."""
    assert DeploymentStatus.to_human_readable(status) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("src", "src"),
        ("src/app", "src/app"),
        ("  src/app  ", "src/app"),
        ("my-app", "my-app"),
        ("my_app", "my_app"),
        ("my.app", "my.app"),
        ("src/my app", "src/my app"),
        ("a/b/c", "a/b/c"),
    ],
)
def test_validate_app_directory_valid(value: str | None, expected: str | None) -> None:
    """Should accept valid directory values and normalize them."""
    assert validate_app_directory(value) == expected


@pytest.mark.parametrize(
    "value,expected_message",
    [
        ("~/src", "cannot start with '~'"),
        ("/absolute/path", "must be a relative path, not absolute"),
        ("src/../etc", "cannot contain '..' path segments"),
        ("..", "cannot contain '..' path segments"),
        ("src/../../etc", "cannot contain '..' path segments"),
        (
            "src/@app",
            "contains invalid characters (allowed: letters, numbers, space, / . _ -)",
        ),
        (
            "src/$app",
            "contains invalid characters (allowed: letters, numbers, space, / . _ -)",
        ),
        (
            "src/app!",
            "contains invalid characters (allowed: letters, numbers, space, / . _ -)",
        ),
        (
            "src/app#1",
            "contains invalid characters (allowed: letters, numbers, space, / . _ -)",
        ),
    ],
)
def test_validate_app_directory_invalid(value: str, expected_message: str) -> None:
    """Should reject invalid directory values with descriptive errors."""
    with pytest.raises(ValueError) as exc_info:
        validate_app_directory(value)

    assert str(exc_info.value) == expected_message


def test_get_large_files_no_files_above_threshold(tmp_path: Path) -> None:
    """Should not return files smaller than the threshold."""
    _create_file(tmp_path / "small.bin", 512 * 1024)  # 0.5 MB

    assert _get_large_files(tmp_path, threshold_mb=1) == []


def test_get_large_files_returns_files_at_or_above_threshold(tmp_path: Path) -> None:
    """Should return files at or above the threshold with sizes and relative paths."""
    _create_file(tmp_path / "big.bin", 2 * 1024 * 1024)  # 2 MB
    _create_file(tmp_path / "subdir" / "huge.bin", 5 * 1024 * 1024)  # 5 MB
    _create_file(tmp_path / "small.bin", 100 * 1024)  # 0.1 MB

    result = _get_large_files(tmp_path, threshold_mb=1)

    assert sorted(result, key=lambda x: x[1]) == [
        (Path("big.bin"), 2 * 1024 * 1024),
        (Path("subdir") / "huge.bin", 5 * 1024 * 1024),
    ]


def test_get_large_files_excludes_default_exclusions(tmp_path: Path) -> None:
    """Should not count files in excluded directories like .venv or __pycache__."""
    _create_file(tmp_path / ".venv" / "lib" / "huge.so", 5 * 1024 * 1024)
    _create_file(tmp_path / "__pycache__" / "module.cpython-311.pyc", 5 * 1024 * 1024)
    _create_file(tmp_path / "main.py", 5 * 1024 * 1024)

    assert _get_large_files(tmp_path, threshold_mb=1) == [
        (Path("main.py"), 5 * 1024 * 1024)
    ]


def test_get_large_files_respects_fastapicloudignore(tmp_path: Path) -> None:
    """Should not count files matching .fastapicloudignore patterns."""
    _create_file(tmp_path / "data" / "huge.bin", 5 * 1024 * 1024)
    _create_file(tmp_path / "main.bin", 5 * 1024 * 1024)
    (tmp_path / ".fastapicloudignore").write_text("data/\n")

    assert _get_large_files(tmp_path, threshold_mb=1) == [
        (Path("main.bin"), 5 * 1024 * 1024)
    ]
