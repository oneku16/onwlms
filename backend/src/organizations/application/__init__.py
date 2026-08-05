"""Public organization application capabilities and contracts."""

from organizations.application.ports import CampusDirectory
from organizations.application.ports import CampusRepository
from organizations.application.ports import OrganizationAuditSink
from organizations.application.ports import OrganizationRepository
from organizations.application.service import CONFIGURE_ORGANIZATION_PERMISSION
from organizations.application.service import CREATE_ORGANIZATION_PERMISSION
from organizations.application.service import LIFECYCLE_PERMISSION
from organizations.application.service import MANAGE_CAMPUSES_PERMISSION
from organizations.application.service import READ_ORGANIZATION_PERMISSION
from organizations.application.service import OrganizationService

__all__ = [
    "CONFIGURE_ORGANIZATION_PERMISSION",
    "CREATE_ORGANIZATION_PERMISSION",
    "LIFECYCLE_PERMISSION",
    "MANAGE_CAMPUSES_PERMISSION",
    "READ_ORGANIZATION_PERMISSION",
    "CampusDirectory",
    "CampusRepository",
    "OrganizationAuditSink",
    "OrganizationRepository",
    "OrganizationService",
]
