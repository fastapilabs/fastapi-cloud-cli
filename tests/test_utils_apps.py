from pathlib import Path

from fastapi_cloud_cli.utils.apps import AppConfig, resolve_app_id


def test_resolve_app_id_prefers_explicit_app_id(tmp_path: Path) -> None:
    cloud_dir = tmp_path / ".fastapicloud"
    cloud_dir.mkdir()
    (cloud_dir / "cloud.json").write_text(
        AppConfig(app_id="linked-app", team_id="team").model_dump_json(),
        encoding="utf-8",
    )

    assert resolve_app_id(app_id="explicit-app", path=tmp_path) == "explicit-app"


def test_resolve_app_id_uses_linked_app(tmp_path: Path) -> None:
    cloud_dir = tmp_path / ".fastapicloud"
    cloud_dir.mkdir()
    (cloud_dir / "cloud.json").write_text(
        AppConfig(app_id="linked-app", team_id="team").model_dump_json(),
        encoding="utf-8",
    )

    assert resolve_app_id(path=tmp_path) == "linked-app"


def test_resolve_app_id_returns_none_without_app_context(tmp_path: Path) -> None:
    assert resolve_app_id(path=tmp_path) is None
