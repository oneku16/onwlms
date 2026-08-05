"""Explicit people module construction and route registration."""

from dataclasses import dataclass

from fastapi import FastAPI

from people.application.ports import OrganizationAvailability
from people.application.ports import PeopleAuditSink
from people.application.ports import ProfileActivationWriter
from people.application.reference_service import PeopleReferenceService
from people.application.service import MembershipService
from people.application.service import PeopleService
from people.infrastructure.repositories import SQLAlchemyMembershipRepository
from people.infrastructure.repositories import SQLAlchemyPeopleRepository
from people.presentation.router import router
from shared.database import Database


@dataclass(frozen=True, slots=True)
class PeopleResources:
    """Expose the separately addressable people and membership services."""

    people: PeopleService
    memberships: MembershipService
    references: PeopleReferenceService


def create_people_resources(
    *,
    database: Database,
    pii_encryption_key: str,
    organizations: OrganizationAvailability,
    audit: PeopleAuditSink,
    profile_activations: ProfileActivationWriter | None = None,
) -> PeopleResources:
    """Construct encrypted PostgreSQL people and membership adapters."""

    if not pii_encryption_key:
        message = "A dedicated PII encryption key is required"
        raise ValueError(message)
    people = SQLAlchemyPeopleRepository(
        database=database,
        encryption_key=pii_encryption_key,
    )
    memberships = SQLAlchemyMembershipRepository(database)
    return PeopleResources(
        people=PeopleService(
            people=people,
            audit=audit,
            profile_activations=profile_activations,
        ),
        memberships=MembershipService(
            memberships=memberships,
            people=people,
            organizations=organizations,
            audit=audit,
        ),
        references=PeopleReferenceService(repository=people),
    )


def install_people_routes(
    *,
    app: FastAPI,
    resources: PeopleResources,
) -> None:
    """Register people services and their thin router on one application."""

    app.state.people_service = resources.people
    app.state.membership_service = resources.memberships
    app.include_router(router)


__all__ = [
    "PeopleResources",
    "create_people_resources",
    "install_people_routes",
]
