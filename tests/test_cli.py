import json
import subprocess
import sys
from datetime import datetime, timezone

import pytest
import typer
from pydantic import BaseModel
from rich.console import Console, RenderableType
from rich.text import Text
from rich.theme import Theme
from rich_toolkit import RichToolkit
from rich_toolkit.container import Container
from rich_toolkit.element import Element
from rich_toolkit.input import Input
from rich_toolkit.progress import Progress
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.utils import cli as cli_utils
from fastapi_cloud_cli.utils.cli import (
    ERROR_BULLET,
    FastAPIRichToolkit,
    FastAPIStyle,
    IndentedBlock,
    get_details_table,
    get_rich_toolkit,
)
from fastapi_cloud_cli.utils.config import get_version_check_cache_path
from fastapi_cloud_cli.utils.errors import ErrorCode
from fastapi_cloud_cli.utils.execution import JsonOutputOption
from fastapi_cloud_cli.utils.version_check import write_latest_version_cache

runner = CliRunner()


class AuthStatus(BaseModel):
    authenticated: bool


class MetricsOutput(BaseModel):
    cpu: float


def render_plain(renderable: RenderableType, *, width: int = 80) -> str:
    console = Console(width=width, color_system=None)
    return "".join(
        segment.text for segment in console.render(renderable, console.options)
    )


def style_with_recording_console(*, force_terminal: bool) -> FastAPIStyle:
    style = FastAPIStyle()
    style.console = Console(
        force_terminal=force_terminal,
        record=True,
        width=20,
        color_system=None,
        theme=Theme({"tag.title": "#ffffff on #009485"}),
    )
    return style


def test_shows_help() -> None:
    result = runner.invoke(app, ["cloud", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_shows_help_without_args() -> None:
    result = runner.invoke(app, ["cloud"])

    assert result.exit_code == 2
    assert "Usage:" in result.output


def test_script() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "fastapi_cloud_cli", "--help"],
        capture_output=True,
        encoding="utf-8",
    )
    assert "Usage" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["cloud", "--version"])
    assert result.exit_code == 0, result.output
    assert "FastAPI Cloud CLI version:" in result.output


def test_uses_header_style() -> None:
    toolkit = get_rich_toolkit()
    assert isinstance(toolkit, FastAPIRichToolkit)
    assert isinstance(toolkit.style, FastAPIStyle)


def test_title_sweep_frames_keep_constant_chip_width() -> None:
    chip = " Deploy "
    frames = list(cli_utils._title_sweep_frames("Deploy"))

    assert frames[0] == ("", "", " " * len(chip))
    assert frames[-1] == (chip, "", "")
    assert all(len("".join(frame)) == len(chip) for frame in frames)
    assert any(shades for _, shades, _ in frames)


def test_strip_rich_markup_preserves_empty_hint() -> None:
    assert cli_utils._strip_rich_markup(None) is None


def test_indented_block_hangs_prefix_and_preserves_final_blank_line() -> None:
    block = IndentedBlock(
        Text("alpha\nbeta\n"),
        first_prefix=Text("> "),
        prefix=Text("| "),
    )

    assert render_plain(block, width=20) == "> alpha\n| beta\n\u200b\n"


def test_fastapi_style_returns_parent_rendered_children_without_extra_indent() -> None:
    style = FastAPIStyle()
    parent = Container(style=style)

    assert style.render_element("child", parent=parent) == "child"


def test_fastapi_style_uses_child_metadata_from_container() -> None:
    style = FastAPIStyle()
    container = Container(style=style)
    container.elements = [Input(value="abc", style=style, bullet=False)]

    assert (
        render_plain(style.render_element(container), width=20) == "  abc\n\n\u200b\n"
    )


def test_fastapi_style_renders_title_chip_and_tagged_title() -> None:
    style = FastAPIStyle(theme={"tag.title": "#ffffff on #009485"})

    assert render_plain(style.render_element("Deploy", title=True)) == "  Deploy \n"
    assert (
        render_plain(
            style.render_element("Deploy app", title=True, tag="cloud", emoji="🚀")
        )
        == "  cloud \n\n 🚀 Deploy app\n"
    )


def test_fastapi_style_skips_title_animation_for_non_terminal_console() -> None:
    style = style_with_recording_console(force_terminal=False)

    style.render_element("Deploy", title=True, animate=True)

    assert style.console.export_text() == ""


def test_fastapi_style_animates_title_sweep_in_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_utils, "TITLE_SWEEP_DELAY", 0)
    style = style_with_recording_console(force_terminal=True)

    style._animate_title_sweep("Go")

    assert " Go " in style.console.export_text()


def test_fastapi_style_renders_progress_and_bullet_prefixes() -> None:
    style = FastAPIStyle()
    progress = Progress("Working", style=style, console=style.console)

    assert render_plain(style.render_element("plain", bullet=False)) == "  plain\n"
    assert render_plain(style.render_element("plain", emoji="[green]✓[/]")) == (
        " ✓  plain\n"
    )
    assert render_plain(
        style.render_element(Input(value="abc", style=style, emoji="🚀"))
    ) == (" 🚀 abc\n")
    assert render_plain(style.render_element(progress)) == " 🐤 Working\n"
    assert style._get_bullet_prefix("").plain == "    "
    assert style._get_bullet_prefix("🚀").plain == " 🚀 "


def test_fastapi_style_progress_status_emoji_states() -> None:
    style = FastAPIStyle()
    progress = Progress(
        "Working",
        style=style,
        console=style.console,
    )
    progress.metadata["done_emoji"] = "✅"
    style.animation_counter = 0

    assert style._get_progress_status_emoji(progress, done=False) == "🥚"
    assert style._get_progress_status_emoji(progress, done=True) == "✅"

    progress.metadata["emoji"] = "🤏"
    assert style._get_progress_status_emoji(progress, done=False) == "🤏"
    assert style._get_progress_status_emoji(progress, done=True) == "✅"

    progress._cancelled = True
    assert style._get_progress_status_emoji(progress, done=False) == "🟡"

    progress._cancelled = False
    progress.is_error = True
    assert style._get_progress_status_emoji(progress, done=False) == "🟡"


def test_fastapi_style_gets_cursor_offset_with_and_without_bullet_column() -> None:
    style = FastAPIStyle()

    offset = style.get_cursor_offset_for_element(Element(metadata={"emoji": "🚀"}))
    assert offset.top == 0
    assert offset.left == 4

    offset = style.get_cursor_offset_for_element(Element(metadata={"bullet": False}))
    assert offset.top == 0
    assert offset.left == 2

    input_offset = style.get_cursor_offset_for_element(
        Input(label="Project name", style=style)
    )
    assert input_offset.top == 2
    assert input_offset.left == 4


def test_toolkit_success_delegates_human_output_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolkit = get_rich_toolkit(minimal=True)
    calls: list[tuple[object, object | None]] = []

    def record_output(data: object, render_output: object | None = None) -> None:
        calls.append((data, render_output))

    def render_output(data: AuthStatus, toolkit: RichToolkit) -> None: ...

    monkeypatch.setattr(toolkit, "output", record_output)

    toolkit.success(AuthStatus(authenticated=True), render_output=render_output)

    assert calls == [(AuthStatus(authenticated=True), render_output)]


def test_get_details_table_renders_label_value_rows() -> None:
    table = get_details_table(
        [
            ("Name", "example"),
            ("Region", Text("iad")),
        ]
    )

    assert table.row_count == 2
    assert "Name" in render_plain(table)
    assert "iad" in render_plain(table)


def test_toolkit_success_prints_json_envelope() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command(json_output: JsonOutputOption = False) -> None:
        with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
            toolkit.success(AuthStatus(authenticated=True), hint="next step")

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True},
        "hint": "next step",
    }


def test_toolkit_success_omits_empty_json_envelope_fields() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command(json_output: JsonOutputOption = False) -> None:
        with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
            toolkit.success(AuthStatus(authenticated=True))

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True},
    }


def test_toolkit_success_includes_non_empty_warnings() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command(json_output: JsonOutputOption = False) -> None:
        with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
            toolkit.success(
                AuthStatus(authenticated=True),
                warnings=[{"code": "not_validated", "message": "Token not validated."}],
            )

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True},
        "warnings": [{"code": "not_validated", "message": "Token not validated."}],
    }


def test_toolkit_success_uses_strict_json_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FASTAPI_CLOUD_JSON", "1")
    monkeypatch.setenv("FASTAPI_CLOUD_DISABLE_VERSION_CHECK", "1")

    with get_rich_toolkit(minimal=True, json_output=True) as toolkit:
        with pytest.raises(ValueError, match="Out of range float values"):
            toolkit.success(MetricsOutput(cpu=float("inf")))


def test_toolkit_json_mode_suppresses_update_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_app = typer.Typer()
    monkeypatch.setenv("FASTAPI_CLOUD_DISABLE_VERSION_CHECK", "")
    write_latest_version_cache(
        get_version_check_cache_path(),
        latest_version="999.0.0",
        now=datetime.now(timezone.utc),
    )

    @test_app.command()
    def command(json_output: JsonOutputOption = False) -> None:
        with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
            toolkit.success(AuthStatus(authenticated=True))

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True},
    }


def test_toolkit_fail_prints_json_error_and_exits() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command(json_output: JsonOutputOption = False) -> None:
        with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
            toolkit.fail(
                "api_error",
                "[bold]A value is required.[/]",
                hint="Pass [blue]--value[/].",
            )

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "api_error",
            "message": "A value is required.",
            "hint": "Pass --value.",
        }
    }


def test_toolkit_fail_uses_error_emoji(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    with get_rich_toolkit() as toolkit:

        def record_print(
            *renderables: object,
            end: str = "\n",
            **metadata: object,
        ) -> None:
            calls.append(metadata)

        monkeypatch.setattr(toolkit, "print", record_print)

        with pytest.raises(typer.Exit):
            toolkit.fail("api_error", "A value is required.")

    assert calls[0]["emoji"] == ERROR_BULLET


def test_toolkit_fail_uses_custom_human_output_renderer_and_exits() -> None:
    test_app = typer.Typer()

    def render_output(
        toolkit: RichToolkit,
        *,
        code: ErrorCode,
        message: str,
        hint: str,
    ) -> None:
        toolkit.print(f"{code}: {message} {hint}")

    @test_app.command()
    def command() -> None:
        with get_rich_toolkit(minimal=True) as toolkit:
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                render_output=render_output,
            )

    result = runner.invoke(test_app)

    assert result.exit_code == 1
    assert "not_logged_in: No credentials found." in result.output


def test_embedded_fastapi_cli_prints_forced_update_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_app = typer.Typer()
    parent_app.add_typer(app)
    monkeypatch.setattr(sys, "argv", ["fastapi", "cloud", "whoami"])
    write_latest_version_cache(
        get_version_check_cache_path(),
        latest_version="999.0.0",
        now=datetime.now(timezone.utc),
    )

    result = runner.invoke(
        parent_app,
        ["cloud", "whoami"],
        env={"FASTAPI_CLOUD_DISABLE_VERSION_CHECK": ""},
    )

    assert result.exit_code == 1, result.output
    assert "No credentials found" in result.output
    assert "A newer FastAPI Cloud CLI version is available" in result.output
    assert "→ 999.0.0" in result.output
