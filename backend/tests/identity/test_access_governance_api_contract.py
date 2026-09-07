"""Contract coverage for membership and platform access governance routes."""

from fastapi.routing import APIRoute

from entitlements.presentation.router import router as entitlement_router
from identity.presentation.router import platform_router
from identity.presentation.router import router as identity_router
from people.presentation.router import router as people_router


def test_access_governance_routes_are_explicit() -> None:
    """Keep lifecycle and platform-administration paths visible to clients."""

    paths_and_methods = {
        (route.path, method)
        for router in (people_router, platform_router)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
    }

    assert {
        ("/api/v1/memberships", "GET"),
        ("/api/v1/memberships/{membership_id}/suspend", "POST"),
        ("/api/v1/memberships/{membership_id}/reactivate", "POST"),
        ("/api/v1/memberships/{membership_id}/revoke", "POST"),
        ("/api/v1/platform/organizations/{organization_id}/owners", "GET"),
        (
            "/api/v1/platform/organizations/{organization_id}/owners/"
            "{membership_id}/suspend",
            "POST",
        ),
        (
            "/api/v1/platform/organizations/{organization_id}/owners/"
            "{membership_id}/revoke",
            "POST",
        ),
        ("/api/v1/platform/administrators/bootstrap", "POST"),
        ("/api/v1/platform/administrators", "GET"),
        ("/api/v1/platform/administrators/{subject_id}/assign", "POST"),
        ("/api/v1/platform/administrators/{subject_id}/revoke", "POST"),
    }.issubset(paths_and_methods)


def test_frontend_governance_reads_have_typed_response_contracts() -> None:
    """Prevent critical generated client responses from degrading to objects."""

    typed_paths = {
        route.path
        for router in (
            identity_router,
            people_router,
            platform_router,
            entitlement_router,
        )
        for route in router.routes
        if isinstance(route, APIRoute) and route.response_model is not None
    }

    assert {
        "/api/v1/auth/me",
        "/api/v1/auth/memberships",
        "/api/v1/memberships",
        "/api/v1/platform/organizations/{organization_id}/owners",
        "/api/v1/platform/administrators",
        "/api/v1/platform/features",
        "/api/v1/platform/plans",
    }.issubset(typed_paths)
