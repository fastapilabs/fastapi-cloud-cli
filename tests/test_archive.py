import tarfile
from pathlib import Path

import pytest

from fastapi_cloud_cli.commands.deploy import archive


@pytest.fixture
def src_path(tmp_path: Path) -> Path:
    path = tmp_path / "source"
    path.mkdir()
    return path


@pytest.fixture
def tar_path(tmp_path: Path) -> Path:
    return tmp_path / "archive.tar"


def test_archive_creates_tar_file(src_path: Path, tar_path: Path) -> None:
    (src_path / "main.py").write_text("print('hello')")
    (src_path / "config.json").write_text('{"key": "value"}')
    (src_path / "subdir").mkdir()
    (src_path / "subdir" / "utils.py").write_text("def helper(): pass")

    archive(src_path, tar_path)
    assert tar_path.exists()


def test_archive_excludes_venv_and_similar_folders(
    src_path: Path, tar_path: Path
) -> None:
    """Should exclude .venv directory from archive."""
    # the only files we want to include
    (src_path / "main.py").write_text("print('hello')")
    (src_path / "static").mkdir()
    (src_path / "static" / "index.html").write_text("<html></html>")
    # virtualenv
    (src_path / ".venv").mkdir()
    (src_path / ".venv" / "lib").mkdir()
    (src_path / ".venv" / "lib" / "package.py").write_text("# package")
    # pycache
    (src_path / "__pycache__").mkdir()
    (src_path / "__pycache__" / "main.cpython-311.pyc").write_text("bytecode")
    # pyc files
    (src_path / "main.pyc").write_text("bytecode")
    # mypy/pytest
    (src_path / ".mypy_cache").mkdir()
    (src_path / ".mypy_cache" / "file.json").write_text("{}")
    (src_path / ".pytest_cache").mkdir()
    (src_path / ".pytest_cache" / "cache.db").write_text("data")

    archive(src_path, tar_path)

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert set(names) == {"main.py", "static/index.html"}


def test_archive_preserves_relative_paths(src_path: Path, tar_path: Path) -> None:
    (src_path / "src").mkdir()
    (src_path / "src" / "app").mkdir()
    (src_path / "src" / "app" / "main.py").write_text("print('hello')")

    archive(src_path, tar_path)

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert names == ["src/app/main.py"]


def test_archive_respects_fastapicloudignore(src_path: Path, tar_path: Path) -> None:
    """Should exclude files specified in .fastapicloudignore."""
    (src_path / "main.py").write_text("print('hello')")
    (src_path / "config.py").write_text("CONFIG = 'value'")
    (src_path / "secrets.env").write_text("SECRET_KEY=xyz")
    (src_path / "data").mkdir()
    (src_path / "data" / "file.txt").write_text("data")

    (src_path / ".fastapicloudignore").write_text("secrets.env\ndata/\n")

    archive(src_path, tar_path)

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert set(names) == {
            "main.py",
            "config.py",
        }


def test_archive_respects_fastapicloudignore_unignore(
    src_path: Path, tar_path: Path
) -> None:
    """Test we can use .fastapicloudignore to unignore files inside .gitignore"""
    (src_path / "main.py").write_text("print('hello')")

    (src_path / "ignore_me.txt").write_text("You should ignore me")

    (src_path / "static/build").mkdir(exist_ok=True, parents=True)
    (src_path / "static/build/style.css").write_text("body { background: #bada55 }")

    # Rignore needs a .git folder to make .gitignore work
    (src_path / ".git").mkdir(exist_ok=True, parents=True)
    (src_path / ".gitignore").write_text("ignore_me.txt\nbuild/")

    (src_path / ".fastapicloudignore").write_text("!static/build")

    archive(src_path, tar_path)

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert set(names) == {"main.py", "static/build/style.css"}


def test_archive_includes_hidden_files(src_path: Path, tar_path: Path) -> None:
    """Should include hidden files in the archive by default."""
    (src_path / "main.py").write_text("print('hello')")
    (src_path / ".env").write_text("SECRET_KEY=xyz")
    (src_path / ".config").mkdir()
    (src_path / ".config" / "settings.json").write_text('{"setting": "value"}')

    archive(src_path, tar_path)

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert set(names) == {
            "main.py",
            ".env",
            ".config/settings.json",
        }
