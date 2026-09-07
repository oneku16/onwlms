"""PostgreSQL outbox worker process with bounded polling and graceful shutdown."""

import asyncio
import signal
import socket

import structlog

from audit.application.service import AuditService
from audit.infrastructure.repository import SQLAlchemyAuditRepository
from audit.infrastructure.sinks import ApplicationAuditSink
from core.identifiers import new_uuid7
from core.logging import configure_logging
from core.settings import Settings
from outbox.application.worker import OutboxWorker
from outbox.infrastructure.repository import SQLAlchemyOutboxRepository
from provisioning.application.handler import ActivationProvisioningHandler
from provisioning.composition import create_provisioning_service
from shared.database import Database


async def run_worker(settings: Settings | None = None) -> None:
    """Poll due events until the process receives a termination signal."""

    app_settings = settings or Settings()
    configure_logging()
    database = Database(
        app_settings,
        database_url=app_settings.WORKER_DATABASE_URL,
    )
    provisioning = create_provisioning_service(
        settings=app_settings,
        database=database,
        audit=ApplicationAuditSink(AuditService(SQLAlchemyAuditRepository(database))),
    )
    worker = OutboxWorker(
        repository=SQLAlchemyOutboxRepository(database),
        handlers=[ActivationProvisioningHandler(provisioning)],
        worker_id=f"{socket.gethostname()}-{new_uuid7()}",
        max_attempts=app_settings.WORKER_MAX_ATTEMPTS,
        lease_seconds=app_settings.WORKER_LEASE_SECONDS,
    )
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stopping.set)
    logger = structlog.get_logger("worker")
    logger.info("worker_started")
    try:
        while not stopping.is_set():
            processed = await worker.process_batch()
            if processed == 0:
                try:
                    await asyncio.wait_for(
                        stopping.wait(),
                        timeout=app_settings.WORKER_POLL_SECONDS,
                    )
                except TimeoutError:
                    continue
    finally:
        await database.close()
        logger.info("worker_stopped")


def main() -> None:
    """Run the asynchronous worker from the container entry point."""

    asyncio.run(run_worker())


if __name__ == "__main__":
    main()


__all__ = ["main", "run_worker"]
