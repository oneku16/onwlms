"""Organization lifecycle, branding, configuration, and campus domain values."""

import re
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from organizations.domain.exceptions import InvalidOrganizationError
from organizations.domain.exceptions import OrganizationLifecycleError

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$"
)


class OrganizationType(StrEnum):
    """Supported institutional categories without privileging one workflow."""

    SCHOOL = "school"
    COLLEGE = "college"
    UNIVERSITY = "university"
    INSTITUTE = "institute"


class OrganizationStatus(StrEnum):
    """Govern whether a tenant may continue ordinary operations."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class EducationMode(StrEnum):
    """Select the organization-level curriculum configuration foundation."""

    FIXED = "fixed"
    FLEXIBLE = "flexible"
    HYBRID = "hybrid"


class DomainVerificationStatus(StrEnum):
    """Track custom-domain verification without performing DNS automation."""

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LogoMetadata:
    """Describe a validated logo object without embedding file content or URL."""

    file_name: str
    content_type: str
    size_bytes: int
    object_key: str = field(repr=False)

    def __post_init__(self) -> None:
        """Reject unsafe or implausible logo metadata at the owning boundary."""

        allowed_types = frozenset({"image/jpeg", "image/png", "image/webp"})
        if (
            not self.file_name
            or "/" in self.file_name
            or "\\" in self.file_name
            or self.content_type not in allowed_types
            or self.size_bytes <= 0
            or self.size_bytes > 5_000_000
            or not self.object_key
        ):
            raise InvalidOrganizationError("Invalid logo metadata")


@dataclass(frozen=True, slots=True)
class OrganizationBranding:
    """Represent tenant-owned display branding with strict color metadata."""

    display_name: str
    primary_color: str = "#1D4ED8"
    secondary_color: str = "#0F172A"
    logo: LogoMetadata | None = None

    def __post_init__(self) -> None:
        """Validate display text and exact six-digit hexadecimal colors."""

        if not self.display_name.strip() or len(self.display_name) > 200:
            raise InvalidOrganizationError("Invalid organization display name")
        if not _COLOR_PATTERN.fullmatch(
            self.primary_color
        ) or not _COLOR_PATTERN.fullmatch(self.secondary_color):
            raise InvalidOrganizationError("Brand colors must be hexadecimal")


@dataclass(frozen=True, slots=True)
class CustomDomainMetadata:
    """Describe custom-domain verification state without DNS credentials."""

    domain: str
    verification_status: DomainVerificationStatus

    def __post_init__(self) -> None:
        """Reject schemes, paths, ports, and malformed host names."""

        if self.domain != self.domain.lower() or not _DOMAIN_PATTERN.fullmatch(
            self.domain
        ):
            raise InvalidOrganizationError("Invalid custom domain")


@dataclass(frozen=True, slots=True)
class OrganizationConfiguration:
    """Contain non-secret tenant settings owned by organization governance."""

    locale: str
    timezone: str
    education_mode: EducationMode
    custom_domain: CustomDomainMetadata | None = None
    ownid_tenant_reference: str | None = None
    ownid_client_reference: str | None = None

    def __post_init__(self) -> None:
        """Validate locale, time zone, and non-secret OwnID references."""

        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", self.locale):
            raise InvalidOrganizationError("Invalid locale")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise InvalidOrganizationError("Invalid timezone") from exc
        references = (
            self.ownid_tenant_reference,
            self.ownid_client_reference,
        )
        if any(
            reference is not None and len(reference) > 255 for reference in references
        ):
            raise InvalidOrganizationError("Provider reference is too long")


@dataclass(frozen=True, slots=True)
class Organization:
    """Represent one tenant and protect its lifecycle transitions."""

    id: UUID
    slug: str
    organization_type: OrganizationType
    status: OrganizationStatus
    branding: OrganizationBranding
    configuration: OrganizationConfiguration

    def __post_init__(self) -> None:
        """Validate the stable organization slug."""

        if len(self.slug) > 80 or not _SLUG_PATTERN.fullmatch(self.slug):
            raise InvalidOrganizationError("Invalid organization slug")

    def suspend(self) -> Organization:
        """Return the suspended lifecycle state and reject repeated suspension."""

        if self.status is OrganizationStatus.SUSPENDED:
            raise OrganizationLifecycleError("Organization is already suspended")
        return replace(self, status=OrganizationStatus.SUSPENDED)

    def reactivate(self) -> Organization:
        """Return the active lifecycle state and reject repeated activation."""

        if self.status is OrganizationStatus.ACTIVE:
            raise OrganizationLifecycleError("Organization is already active")
        return replace(self, status=OrganizationStatus.ACTIVE)

    def configure(
        self,
        *,
        branding: OrganizationBranding,
        configuration: OrganizationConfiguration,
    ) -> Organization:
        """Return an organization with validated tenant-owned configuration."""

        if self.status is OrganizationStatus.SUSPENDED:
            raise OrganizationLifecycleError(
                "Suspended organizations cannot change configuration"
            )
        return replace(self, branding=branding, configuration=configuration)


@dataclass(frozen=True, slots=True)
class Campus:
    """Represent one organization-owned physical or administrative campus."""

    id: UUID
    organization_id: UUID
    code: str
    name: str
    active: bool = True

    def __post_init__(self) -> None:
        """Validate a tenant-local code and display name."""

        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,31}", self.code):
            raise InvalidOrganizationError("Invalid campus code")
        if not self.name.strip() or len(self.name) > 200:
            raise InvalidOrganizationError("Invalid campus name")


__all__ = [
    "Campus",
    "CustomDomainMetadata",
    "DomainVerificationStatus",
    "EducationMode",
    "LogoMetadata",
    "Organization",
    "OrganizationBranding",
    "OrganizationConfiguration",
    "OrganizationStatus",
    "OrganizationType",
]
