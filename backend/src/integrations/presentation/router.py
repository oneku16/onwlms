"""Thin Moodle configuration and status routes."""

from collections.abc import Awaitable
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretStr

from core.context import ActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from integrations.application.service import MoodleIntegrationService
from integrations.domain.moodle import MoodleConfiguration


class MoodleConfigurationRequest(BaseModel):
    """Validate tenant Moodle endpoint and credential input."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=12, max_length=500)
    token: SecretStr


class MoodleStatusResponse(BaseModel):
    """Safe integration status without credential or provider payload."""

    model_config = ConfigDict(extra="forbid")

    configured: bool
    base_url: str | None
    status: str
    last_success_at: str | None
    last_error_code: str | None


def create_integrations_router(
    *,
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
    csrf_dependency: Callable[..., Awaitable[None]],
) -> APIRouter:
    """Create tenant integration routes with injected security dependencies."""

    router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

    @router.get("/moodle/status")
    async def moodle_status(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> MoodleStatusResponse:
        """Return safe Moodle synchronization and activation status."""

        tenant_actor = _tenant_actor(actor)
        service: MoodleIntegrationService = request.app.state.moodle_service
        configuration = await service.status(actor=tenant_actor)
        return _status_response(configuration)

    @router.put("/moodle/configuration")
    async def configure_moodle(
        payload: MoodleConfigurationRequest,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> MoodleStatusResponse:
        """Activate or rotate one tenant's Moodle integration."""

        tenant_actor = _tenant_actor(actor)
        service: MoodleIntegrationService = request.app.state.moodle_service
        configuration = await service.configure(
            actor=tenant_actor,
            base_url=payload.base_url,
            token=payload.token.get_secret_value(),
        )
        return _status_response(configuration)

    return router


def _tenant_actor(actor: ActorContext) -> TenantActorContext:
    """Reject platform context on ordinary tenant integration routes."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _status_response(
    configuration: MoodleConfiguration | None,
) -> MoodleStatusResponse:
    """Serialize integration metadata without credential material."""

    if configuration is None:
        return MoodleStatusResponse(
            configured=False,
            base_url=None,
            status="disabled",
            last_success_at=None,
            last_error_code=None,
        )
    return MoodleStatusResponse(
        configured=True,
        base_url=configuration.base_url,
        status=configuration.status.value,
        last_success_at=(
            configuration.last_success_at.isoformat()
            if configuration.last_success_at
            else None
        ),
        last_error_code=configuration.last_error_code,
    )


__all__ = ["create_integrations_router"]
