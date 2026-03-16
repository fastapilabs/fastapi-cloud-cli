from pathlib import Path

import pytest

from fastapi_cloud_cli.commands.deploy import (
    _should_exclude_entry,
    validate_app_directory,
)
from fastapi_cloud_cli.utils.api import DeploymentStatus


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
        (DeploymentStatus.waiting_upload, "Waiting for upload"),
        (DeploymentStatus.ready_for_build, "Ready for build"),
        (DeploymentStatus.building, "Building"),
        (DeploymentStatus.extracting, "Extracting"),
        (DeploymentStatus.extracting_failed, "Extracting failed"),
        (DeploymentStatus.building_image, "Building image"),
        (DeploymentStatus.building_image_failed, "Build failed"),
        (DeploymentStatus.deploying, "Deploying"),
        (DeploymentStatus.deploying_failed, "Deploying failed"),
        (DeploymentStatus.verifying, "Verifying"),
        (DeploymentStatus.verifying_failed, "Verifying failed"),
        (DeploymentStatus.verifying_skipped, "Verification skipped"),
        (DeploymentStatus.success, "Success"),
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
