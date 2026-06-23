import json
from unittest.mock import patch

from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.setup_ci import _get_workflow_content

runner = CliRunner()


def test_print_workflow_uses_default_branch() -> None:
    with patch(
        "fastapi_cloud_cli.commands.ci.print_workflow._get_default_branch",
        return_value="develop",
    ):
        result = runner.invoke(app, ["ci", "print-workflow"])

    assert result.exit_code == 0
    assert result.stdout == _get_workflow_content("develop")
    assert result.stderr == ""


def test_print_workflow_uses_branch_option() -> None:
    result = runner.invoke(app, ["ci", "print-workflow", "--branch", "main"])

    assert result.exit_code == 0
    assert result.stdout == _get_workflow_content("main")
    assert result.stderr == ""


def test_print_workflow_json_outputs_envelope() -> None:
    result = runner.invoke(app, ["ci", "print-workflow", "--branch", "main", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "filename": "deploy.yml",
            "content": _get_workflow_content("main"),
        }
    }
    assert result.stderr == ""
