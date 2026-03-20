from __future__ import annotations

from pathlib import Path


def test_build_alembic_config_uses_cwd_ini_and_resolves_script_location(
    tmp_path: Path, monkeypatch
):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from kfabric.main import _build_alembic_config

    config = _build_alembic_config()

    assert Path(config.config_file_name) == alembic_ini
    assert config.get_main_option("script_location") == str(migrations_dir.resolve())


def test_run_worker_delegates_to_celery_worker_main(monkeypatch):
    from kfabric import main
    from kfabric.workers.celery_app import celery_app

    captured: dict[str, object] = {}

    def fake_worker_main(argv):
        captured["argv"] = argv

    monkeypatch.setattr(celery_app, "worker_main", fake_worker_main)

    main.run_worker()

    assert captured["argv"] == ["worker", "--loglevel=INFO"]
