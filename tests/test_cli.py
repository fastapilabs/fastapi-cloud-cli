import subprocess
import sys


def test_script() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "fastapi_cloud_cli", "--help"],
        capture_output=True,
        encoding="utf-8",
    )
    assert "Usage" in result.stdout
