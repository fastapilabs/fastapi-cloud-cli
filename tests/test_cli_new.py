import shutil

import pytest
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app

runner = CliRunner()


@pytest.fixture
def temp_project_dir(tmp_path, monkeypatch):
    """Create a temporary directory and cd into it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def check_uv_installed():
    """Skip tests if uv is not installed."""
    if not shutil.which("uv"):
        pytest.skip("uv is not installed")


class TestNewCommand:

    def test_creates_project_successfully(self, temp_project_dir):
        result = runner.invoke(app, ["new", "my_fastapi_project"])

        assert result.exit_code == 0
        project_path = temp_project_dir / "my_fastapi_project"
        assert (project_path / "main.py").exists()
        assert (project_path / "README.md").exists()
        assert (project_path / "pyproject.toml").exists()
        assert "Success!" in result.output
        assert "my_fastapi_project" in result.output

    def test_creates_project_with_python_flag(self, temp_project_dir):
        result = runner.invoke(app, ["new", "my_fastapi_project", "--python", "3.12"])

        assert result.exit_code == 0
        project_path = temp_project_dir / "my_fastapi_project"
        assert (project_path / "main.py").exists()
        assert (project_path / "README.md").exists()
        assert (project_path / ".python-version").exists()
        python_version_file = (project_path / ".python-version").read_text()
        assert "3.12" in python_version_file
        assert "Success!" in result.output

    def test_creates_project_with_python_flag_short(self, temp_project_dir):
        result = runner.invoke(app, ["new", "another_project", "-p", "3.9"])
        assert result.exit_code == 0
        project_path = temp_project_dir / "another_project"
        assert (project_path / ".python-version").exists()
        python_version_file = (project_path / ".python-version").read_text()
        assert "3.9" in python_version_file


    def test_creates_project_with_multiple_flags(self, temp_project_dir):
        result = runner.invoke(app, ["new", "my_fastapi_project", "--python", "3.12", "--lib"])

        assert result.exit_code == 0
        project_path = temp_project_dir / "my_fastapi_project"
        # With --lib flag, uv creates a library structure (no main.py by default)
        assert (project_path / "pyproject.toml").exists()
        # Our template files should still be created
        assert (project_path / "main.py").exists()
        assert (project_path / "README.md").exists()

    def test_rejects_python_below_3_8(self, temp_project_dir):
        result = runner.invoke(app, ["new", "my_fastapi_project", "--python", "3.7"])

        assert result.exit_code == 1
        assert "Python 3.7 is not supported" in result.output
        assert "FastAPI requires Python 3.8" in result.output

    def test_rejects_existing_directory(self, temp_project_dir):
        existing_dir = temp_project_dir / "existing_project"
        existing_dir.mkdir()

        result = runner.invoke(app, ["new", "existing_project"])

        assert result.exit_code == 1
        assert f"Directory 'existing_project' already exists." in result.output

    def test_initializes_in_current_directory_when_no_name_provided(self, temp_project_dir):
        result = runner.invoke(app, ["new"])

        assert result.exit_code == 0
        assert "No project name provided" in result.output
        assert "Initializing in current directory" in result.output

        assert "Initialized FastAPI project in current directory" in result.output

        # Files should be created in current directory
        assert (temp_project_dir / "main.py").exists()
        assert (temp_project_dir / "README.md").exists()
        assert (temp_project_dir / "pyproject.toml").exists()

    def test_validate_file_contents(self, temp_project_dir):
        result = runner.invoke(app, ["new", "sample_project"])

        assert result.exit_code == 0
        project_path = temp_project_dir / "sample_project"

        main_py_content = (project_path / "main.py").read_text()
        assert "from fastapi import FastAPI" in main_py_content
        assert "app = FastAPI()" in main_py_content

        readme_content = (project_path / "README.md").read_text()
        assert "# sample_project" in readme_content
        assert "A project created with FastAPI Cloud CLI." in readme_content

    def test_validate_pyproject_toml_contents(self, temp_project_dir):
        result = runner.invoke(app, ["new", "test_project"])

        assert result.exit_code == 0
        project_path = temp_project_dir / "test_project"

        pyproject_content = (project_path / "pyproject.toml").read_text()
        assert 'name = "test-project"' in pyproject_content
        assert 'fastapi[standard]' in pyproject_content
        