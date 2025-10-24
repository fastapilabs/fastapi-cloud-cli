from pathlib import Path

import pytest

from fastapi_cloud_cli.commands.deploy import DeploymentStatus, _should_exclude_entry


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
