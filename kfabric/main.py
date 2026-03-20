import os
from pathlib import Path

from uvicorn import run


def run_api() -> None:
    run("kfabric.api.app:app", host="0.0.0.0", port=8000, reload=False)


def run_worker() -> None:
    from kfabric.workers.celery_app import celery_app

    celery_app.worker_main(["worker", "--loglevel=INFO"])


def run_mcp() -> None:
    from kfabric.mcp.server import run_stdio_server

    run_stdio_server()


def _resolve_alembic_ini() -> Path:
    candidates: list[Path] = []
    configured_path = os.getenv("KFABRIC_ALEMBIC_INI")
    if configured_path:
        candidates.append(Path(configured_path).expanduser())

    candidates.append(Path.cwd() / "alembic.ini")
    candidates.append(Path(__file__).resolve().parent.parent / "alembic.ini")

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    looked_in = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Unable to locate alembic.ini. Looked in: {looked_in}")


def _build_alembic_config():
    from alembic.config import Config

    config_path = _resolve_alembic_ini()
    config = Config(str(config_path))

    script_location = config.get_main_option("script_location")
    if script_location:
        script_path = Path(script_location)
        if not script_path.is_absolute():
            config.set_main_option(
                "script_location",
                str((config_path.parent / script_path).resolve()),
            )

    return config


def run_migrations() -> None:
    from alembic import command

    config = _build_alembic_config()
    command.upgrade(config, "head")
