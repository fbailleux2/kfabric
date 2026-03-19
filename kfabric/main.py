from uvicorn import run


def run_api() -> None:
    run("kfabric.api.app:app", host="0.0.0.0", port=8000, reload=False)


def run_worker() -> None:
    from celery.bin.worker import worker

    from kfabric.workers.celery_app import celery_app

    worker_app = worker.worker(app=celery_app)
    worker_app.run(loglevel="INFO")


def run_mcp() -> None:
    from kfabric.mcp.server import run_stdio_server

    run_stdio_server()

