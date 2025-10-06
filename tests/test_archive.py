import tarfile
from pathlib import Path

from fastapi_cloud_cli.commands.deploy import archive


def test_archive_creates_tar_file(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "config.json").write_text('{"key": "value"}')
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "utils.py").write_text("def helper(): pass")

    tar_path = archive(tmp_path)

    assert tar_path.exists()
    assert tar_path.suffix == ".tar"
    assert tar_path.name.startswith("fastapi-cloud-deploy-")


def test_archive_excludes_venv_and_similar_folders(tmp_path: Path) -> None:
    """Should exclude .venv directory from archive."""
    # the only files we want to include
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "index.html").write_text("<html></html>")
    # virtualenv
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib").mkdir()
    (tmp_path / ".venv" / "lib" / "package.py").write_text("# package")
    # pycache
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-311.pyc").write_text("bytecode")
    # pyc files
    (tmp_path / "main.pyc").write_text("bytecode")
    # mypy/pytest
    (tmp_path / ".mypy_cache").mkdir()
    (tmp_path / ".mypy_cache" / "file.json").write_text("{}")
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / ".pytest_cache" / "cache.db").write_text("data")

    tar_path = archive(tmp_path)

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert set(names) == {"main.py", "static/index.html"}


def test_archive_preserves_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app").mkdir()
    (tmp_path / "src" / "app" / "main.py").write_text("print('hello')")

    tar_path = archive(tmp_path)

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert names == ["src/app/main.py"]


def test_archive_respects_fastapicloudignore(tmp_path: Path) -> None:
    """Should exclude files specified in .fastapicloudignore."""
    # Create test files
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "config.py").write_text("CONFIG = 'value'")
    (tmp_path / "secrets.env").write_text("SECRET_KEY=xyz")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "file.txt").write_text("data")

    # Create .fastapicloudignore file
    (tmp_path / ".fastapicloudignore").write_text("secrets.env\ndata/\n")

    # Create archive
    tar_path = archive(tmp_path)

    # Verify ignored files are excluded
    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert set(names) == {
            "main.py",
            "config.py",
        }


def test_archive_respects_fastapicloudignore_unignore(tmp_path: Path) -> None:
    """Test we can use .fastapicloudignore to unignore files inside .gitignore"""
    # Create test files
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "static/build").mkdir(exist_ok=True, parents=True)
    (tmp_path / "static/build/style.css").write_text("body { background: #bada55 }")
    # Rignore needs a .git folder to make .gitignore work
    (tmp_path / ".git").mkdir(exist_ok=True, parents=True)
    (tmp_path / ".gitignore").write_text("build/")

    # Create .fastapicloudignore file
    (tmp_path / ".fastapicloudignore").write_text("!static/build")

    # Create archive
    tar_path = archive(tmp_path)

    # Verify ignored files are excluded
    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert set(names) == {"main.py", "static/build/style.css"}
