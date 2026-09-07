"""Official MCP SDK adapter exposing only bounded read tools."""

from dataclasses import asdict
from uuid import UUID

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from mcp_gateway.application.service import MCPReadService


def create_mcp_server(
    *,
    service: MCPReadService,
    token_verifier: TokenVerifier,
    issuer_url: str,
    resource_url: str,
) -> FastMCP:
    """Build an OwnID-authenticated, read-only MCP server."""

    server = FastMCP(
        name="OwnSIS",
        instructions=(
            "Read-only official OwnSIS information. Every call revalidates "
            "membership, permission, tenant, resource ownership, and MCP entitlement."
        ),
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer_url),
            resource_server_url=AnyHttpUrl(resource_url),
            required_scopes=["ownsis:mcp:read"],
        ),
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )

    def subject() -> str:
        """Return the verified OwnID subject from MCP authentication context."""

        access_token = get_access_token()
        if access_token is None or not access_token.subject:
            message = "OwnID authentication is required"
            raise PermissionError(message)
        return access_token.subject

    @server.tool(
        name="get_own_schedule",
        description="Get the authenticated student's OwnSIS schedule.",
    )
    async def get_own_schedule(organization_id: str) -> list[dict[str, object]]:
        """Return the current student's authorized schedule."""

        values = await service.own_schedule(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return [asdict(value) for value in values]

    @server.tool(
        name="get_own_official_grades",
        description="Get the authenticated student's official final grades.",
    )
    async def get_own_official_grades(
        organization_id: str,
    ) -> list[dict[str, object]]:
        """Return official grades, never mutable Moodle learning history."""

        values = await service.own_official_grades(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return [asdict(value) for value in values]

    @server.tool(
        name="get_own_upcoming_events",
        description="Get the authenticated student's upcoming academic events.",
    )
    async def get_own_upcoming_events(
        organization_id: str,
    ) -> list[dict[str, object]]:
        """Return upcoming authorized calendar events."""

        values = await service.own_upcoming_events(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return [asdict(value) for value in values]

    @server.tool(
        name="get_own_gpa_summary",
        description="Get the authenticated student's official cumulative GPA.",
    )
    async def get_own_gpa_summary(
        organization_id: str,
    ) -> dict[str, object]:
        """Return official GPA and credit totals without grade history internals."""

        value = await service.own_gpa_summary(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return asdict(value)

    @server.tool(
        name="get_own_moodle_deadlines",
        description="Get Moodle deadline evidence for the current student.",
    )
    async def get_own_moodle_deadlines(
        organization_id: str,
    ) -> list[dict[str, object]]:
        """Return deadline evidence with observation times."""

        values = await service.own_moodle_deadlines(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return [asdict(value) for value in values]

    @server.tool(
        name="get_assigned_sections",
        description="Get sections assigned to the authenticated teacher.",
    )
    async def get_assigned_sections(
        organization_id: str,
    ) -> list[dict[str, object]]:
        """Return teacher-assigned sections."""

        values = await service.assigned_sections(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return [asdict(value) for value in values]

    @server.tool(
        name="get_section_student_list",
        description="Get a student list for a section assigned to the teacher.",
    )
    async def get_section_student_list(
        organization_id: str,
        section_id: str,
    ) -> list[dict[str, object]]:
        """Return a minimum-data authorized section roster."""

        values = await service.section_students(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
            section_id=UUID(section_id),
        )
        return [asdict(value) for value in values]

    @server.tool(
        name="get_grade_synchronization_status",
        description="Get final-grade synchronization status for assigned sections.",
    )
    async def get_grade_synchronization_status(
        organization_id: str,
    ) -> list[dict[str, object]]:
        """Return privacy-safe grade synchronization status."""

        values = await service.grade_sync_status(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return [asdict(value) for value in values]

    @server.tool(
        name="get_linked_student_summaries",
        description="Get summaries for students linked to the authenticated guardian.",
    )
    async def get_linked_student_summaries(
        organization_id: str,
    ) -> list[dict[str, object]]:
        """Return only explicitly linked guardian student summaries."""

        values = await service.linked_student_summaries(
            ownid_subject=subject(),
            organization_id=UUID(organization_id),
        )
        return [asdict(value) for value in values]

    return server


__all__ = ["create_mcp_server"]
