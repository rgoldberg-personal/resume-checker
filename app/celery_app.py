"""Celery application instance and configuration."""
import logging

from celery import Celery
from celery.signals import worker_init

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "cv_analyzer",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Make this the default app so shared_task registers tasks here
celery_app.set_default()

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_default_queue=settings.celery_default_queue,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# Auto-discover tasks in app.tasks package
celery_app.autodiscover_tasks(["app.tasks"])


@worker_init.connect
def on_worker_init(**kwargs: object) -> None:  # noqa: ARG001
    """Start the Platy MCP client once per worker process."""
    from app.mcp_client import init_mcp_client

    logger.info("Initialising Platy MCP client...")
    try:
        init_mcp_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Platy MCP client init failed: %s — salary fallback will be used", exc)
