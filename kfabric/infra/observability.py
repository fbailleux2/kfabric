from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from structlog import configure, get_logger
from structlog.processors import JSONRenderer, TimeStamper
from structlog.stdlib import add_log_level


REQUEST_COUNTER = Counter("kfabric_requests_total", "Number of requests served", ["method", "route", "status_code"])
REQUEST_LATENCY = Histogram("kfabric_request_latency_seconds", "Request latency", ["method", "route"])


def setup_logging() -> None:
    configure(processors=[add_log_level, TimeStamper(fmt="iso"), JSONRenderer()])


def get_metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


logger = get_logger("kfabric")
