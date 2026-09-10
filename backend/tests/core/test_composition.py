"""Production composition-root contract tests without network access."""

from cryptography.fernet import Fernet

from composition import create_application
from core.settings import AppEnvironment
from core.settings import Settings
from shared.database import Database


async def test_full_composition_exposes_operational_routes() -> None:
    """Compose every configured adapter without contacting a provider or database."""

    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        APP_ENV=AppEnvironment.TEST,
        COOKIE_SECURE=False,
        DEV_AUTH_ENABLED=True,
        SESSION_ENCRYPTION_KEY=key,
        PII_ENCRYPTION_KEY=key,
        INTEGRATION_ENCRYPTION_KEY=key,
    )
    database = Database(settings)
    try:
        app = create_application(settings=settings, database=database)
        paths = set(app.openapi()["paths"])
    finally:
        await database.close()

    assert "/api/v1/auth/dev-login" in paths
    assert "/api/v1/platform/organizations" in paths
    assert "/api/v1/people" in paths
    assert "/api/v1/academics/faculties" in paths
    assert "/api/v1/admissions/applications" in paths
    assert "/api/v1/grading/final-grades" in paths
    assert "/api/v1/scheduling/sessions" in paths
    assert "/api/v1/self-service/student/official-grades" in paths
    assert "/api/v1/self-service/teacher/schedule" in paths
    assert "/api/v1/self-service/guardian/linked-students" in paths
    assert "/api/v1/integrations/moodle/status" in paths
    assert "/api/v1/integrations/moodle/grade-event-secret" in paths
    assert "/api/v1/integrations/moodle/grade-events/{organization_id}" in paths
    assert "/api/v1/integrations/moodle/grade-evidence" in paths
    assert "/api/v1/integrations/moodle/grade-reconciliations" in paths
    assert "/api/v1/grading/external-evidence/{evidence_id}/accept" in paths
    assert "/api/v1/operations/provisioning" in paths
    assert "/api/v1/notifications" in paths
    assert "/api/v1/audit" in paths


async def test_mcp_is_mounted_only_when_explicitly_enabled() -> None:
    """Compose the optional authenticated MCP resource and its owned lifespan."""

    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        APP_ENV=AppEnvironment.TEST,
        COOKIE_SECURE=False,
        DEV_AUTH_ENABLED=True,
        SESSION_ENCRYPTION_KEY=key,
        PII_ENCRYPTION_KEY=key,
        INTEGRATION_ENCRYPTION_KEY=key,
        MCP_ENABLED=True,
        MCP_AUDIENCE="urn:ownsis:mcp:test",
        MCP_RESOURCE_URL="http://testserver/mcp",
        OWNID_ISSUER="https://ownid.example.test",
    )
    database = Database(settings)
    try:
        app = create_application(settings=settings, database=database)
        assert any(getattr(route, "path", None) == "/mcp" for route in app.routes)
        async with app.router.lifespan_context(app):
            assert app.state.mcp_server is not None
    finally:
        await database.close()
