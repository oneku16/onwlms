"""Composition helpers for shared portal reads and the optional MCP resource."""

from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi import Request
from mcp.server.auth.provider import TokenVerifier
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from academics.application.read_service import AcademicSelfServiceReadService
from academics.infrastructure.read_repository import (
    SQLAlchemyAcademicSelfServiceReadRepository,
)
from core.context import ActorContext
from core.settings import Settings
from core.time import utc_now
from entitlements.application.ports import EntitlementResolver
from grading.application.read_service import OfficialGradingReadService
from grading.infrastructure.sqlalchemy_repository import SQLAlchemyGradingRepository
from identity.application.read_service import IdentitySubjectReadService
from identity.infrastructure.read_repository import (
    SQLAlchemyIdentitySubjectReadRepository,
)
from integrations.application.ports import MoodleGatewayFactory
from integrations.application.ports import MoodleIntegrationRepository
from integrations.application.read_service import IntegrationSelfServiceReadService
from integrations.infrastructure.read_repository import (
    SQLAlchemyIntegrationEvidenceReadRepository,
)
from mcp_gateway.application.gateway import ApplicationAuthorizedReadGateway
from mcp_gateway.application.owned_read_service import ActorOwnedReadService
from mcp_gateway.application.ports import MCPAuditSink
from mcp_gateway.application.service import MCPReadService
from mcp_gateway.infrastructure.server import create_mcp_server
from mcp_gateway.infrastructure.token_verifier import OwnIDTokenVerifier
from mcp_gateway.presentation.self_service_router import create_self_service_router
from people.application.read_service import PeopleOwnershipReadService
from people.application.service import MembershipService
from people.infrastructure.read_repository import (
    SQLAlchemyPeopleOwnershipReadRepository,
)
from scheduling.application.read_service import OwnedTimetableReadService
from scheduling.infrastructure.sqlalchemy_repository import (
    SQLAlchemySchedulingRepository,
)
from shared.database import Database


@dataclass(frozen=True, slots=True)
class SelfServiceReadResources:
    """Expose the shared actor-bound read policy used by portal and MCP."""

    reads: ActorOwnedReadService


@dataclass(frozen=True, slots=True)
class MCPApplicationResources:
    """Expose the SDK server and its standalone lifespan-owning ASGI app."""

    server: FastMCP
    asgi_app: Starlette

    @asynccontextmanager
    async def mounted_lifespan(self) -> AsyncIterator[None]:
        """Run the SDK session manager when this ASGI app is mounted as a child."""

        async with self.server.session_manager.run():
            yield


def create_self_service_read_resources(
    *,
    settings: Settings,
    database: Database,
    memberships: MembershipService,
    moodle_repository: MoodleIntegrationRepository,
    moodle_gateway_factory: MoodleGatewayFactory,
) -> SelfServiceReadResources:
    """Compose module-owned adapters behind one actor-bound read service."""

    if not settings.PII_ENCRYPTION_KEY:
        raise ValueError("PII_ENCRYPTION_KEY is required for self-service reads")
    people = PeopleOwnershipReadService(
        repository=SQLAlchemyPeopleOwnershipReadRepository(
            database=database,
            encryption_key=settings.PII_ENCRYPTION_KEY,
        ),
        memberships=memberships,
    )
    academics = AcademicSelfServiceReadService(
        SQLAlchemyAcademicSelfServiceReadRepository(database)
    )
    grading = OfficialGradingReadService(SQLAlchemyGradingRepository(database))
    scheduling = OwnedTimetableReadService(SQLAlchemySchedulingRepository(database))
    integrations = IntegrationSelfServiceReadService(
        repository=moodle_repository,
        evidence=SQLAlchemyIntegrationEvidenceReadRepository(database),
        gateway_factory=moodle_gateway_factory,
    )
    return SelfServiceReadResources(
        reads=ActorOwnedReadService(
            people=people,
            academics=academics,
            grading=grading,
            scheduling=scheduling,
            integrations=integrations,
            clock=utc_now,
        )
    )


def install_self_service_routes(
    *,
    app: FastAPI,
    resources: SelfServiceReadResources,
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
) -> None:
    """Install typed cookie-session routes over the shared read policy."""

    app.state.actor_owned_read_service = resources.reads
    app.include_router(
        create_self_service_router(
            service=resources.reads,
            actor_dependency=actor_dependency,
        )
    )


def create_mcp_application(
    *,
    settings: Settings,
    database: Database,
    memberships: MembershipService,
    entitlements: EntitlementResolver,
    audit: MCPAuditSink,
    self_service: SelfServiceReadResources,
    token_verifier: TokenVerifier | None = None,
) -> MCPApplicationResources:
    """Build the authenticated MCP server and standalone ASGI application."""

    if not settings.OWNID_ISSUER:
        raise ValueError("OWNID_ISSUER is required for MCP authentication")
    if not settings.MCP_AUDIENCE:
        raise ValueError("MCP_AUDIENCE is required for MCP authentication")
    verifier = token_verifier or OwnIDTokenVerifier(
        issuer=settings.OWNID_ISSUER,
        audience=settings.MCP_AUDIENCE,
        timeout_seconds=settings.OWNID_HTTP_TIMEOUT_SECONDS,
    )
    gateway = ApplicationAuthorizedReadGateway(
        ownid_issuer=settings.OWNID_ISSUER,
        identities=IdentitySubjectReadService(
            SQLAlchemyIdentitySubjectReadRepository(database)
        ),
        memberships=memberships,
        reads=self_service.reads,
        entitlements=entitlements,
        audit=audit,
        clock=utc_now,
    )
    server = create_mcp_server(
        service=MCPReadService(gateway),
        token_verifier=verifier,
        issuer_url=settings.OWNID_ISSUER,
        resource_url=settings.MCP_RESOURCE_URL,
    )
    return MCPApplicationResources(
        server=server,
        asgi_app=server.streamable_http_app(),
    )


__all__ = [
    "MCPApplicationResources",
    "SelfServiceReadResources",
    "create_mcp_application",
    "create_self_service_read_resources",
    "install_self_service_routes",
]
