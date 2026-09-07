"""Organization-owner membership lifecycle invariants."""

from people.domain.exceptions import InvalidMembershipError
from people.domain.models import Membership
from people.domain.models import MembershipRole
from people.domain.models import MembershipStatus


def suspend_organization_owner(
    membership: Membership,
    owner_memberships: tuple[Membership, ...],
) -> Membership:
    """Suspend an active owner only when another active owner remains."""

    _require_owner_with_active_replacement(
        membership=membership,
        owner_memberships=owner_memberships,
    )
    return membership.suspend()


def revoke_organization_owner(
    membership: Membership,
    owner_memberships: tuple[Membership, ...],
) -> Membership:
    """Terminally revoke an owner only when another active owner remains."""

    if membership.status is MembershipStatus.REVOKED:
        raise InvalidMembershipError("Membership is already revoked")
    _require_owner_with_active_replacement(
        membership=membership,
        owner_memberships=owner_memberships,
    )
    return membership.revoke()


def _require_owner_with_active_replacement(
    *,
    membership: Membership,
    owner_memberships: tuple[Membership, ...],
) -> None:
    """Keep at least one active owner in the exact organization."""

    if MembershipRole.ORGANIZATION_OWNER not in membership.roles:
        raise InvalidMembershipError("Membership is not an organization owner")
    has_active_replacement = any(
        candidate.id != membership.id
        and candidate.organization_id == membership.organization_id
        and MembershipRole.ORGANIZATION_OWNER in candidate.roles
        and candidate.status is MembershipStatus.ACTIVE
        for candidate in owner_memberships
    )
    if not has_active_replacement:
        raise InvalidMembershipError(
            "An organization must retain at least one active owner"
        )


__all__ = [
    "revoke_organization_owner",
    "suspend_organization_owner",
]
