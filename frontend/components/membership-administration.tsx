"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import {
  membershipRoles,
  parseMembershipAdministration,
  type MembershipAdministrationView,
  type MembershipRole,
} from "@/lib/api/administration";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";

const assignableRoles = membershipRoles.filter(
  (role) => role !== "organization_owner",
);

function roleLabel(role: MembershipRole): string {
  return role
    .split("_")
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

export function MembershipAdministration({
  canManage,
  initialMemberships,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly initialMemberships: readonly MembershipAdministrationView[];
  readonly organizationId: string;
}) {
  const [memberships, setMemberships] = useState(initialMemberships);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function replaceMembership(updated: MembershipAdministrationView): void {
    setMemberships((current) =>
      current.map((membership) =>
        membership.id === updated.id ? updated : membership,
      ),
    );
  }

  async function transition(
    membership: MembershipAdministrationView,
    action: "suspend" | "reactivate" | "revoke",
  ): Promise<void> {
    if (
      action === "revoke" &&
      !window.confirm(
        "Revoke this membership? It will immediately lose organization access and cannot be reactivated.",
      )
    ) {
      return;
    }
    setError(null);
    setPendingId(membership.id);
    try {
      replaceMembership(
        await clientApiRequest(
          `/api/v1/memberships/${encodeURIComponent(membership.id)}/${action}`,
          parseMembershipAdministration,
          { method: "POST", organizationId },
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The membership lifecycle change could not be saved.",
      );
    } finally {
      setPendingId(null);
    }
  }

  async function replaceRoles(
    event: FormEvent<HTMLFormElement>,
    membership: MembershipAdministrationView,
  ): Promise<void> {
    event.preventDefault();
    setError(null);
    const roles = new FormData(event.currentTarget)
      .getAll("roles")
      .map(String) as MembershipRole[];
    if (roles.length === 0) {
      setError("Select at least one role for the membership.");
      return;
    }
    setPendingId(membership.id);
    try {
      replaceMembership(
        await clientApiRequest(
          `/api/v1/memberships/${encodeURIComponent(membership.id)}/roles`,
          parseMembershipAdministration,
          {
            method: "PUT",
            organizationId,
            body: { roles },
          },
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The membership roles could not be saved.",
      );
    } finally {
      setPendingId(null);
    }
  }

  if (memberships.length === 0) {
    return (
      <p className="empty-state">
        No memberships are available in this organization.
      </p>
    );
  }

  return (
    <section aria-labelledby="membership-administration-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Authorization lifecycle</p>
          <h2 id="membership-administration-heading">Memberships</h2>
        </div>
      </div>
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      <div className="resource-grid">
        {memberships.map((membership) => {
          const isOwner = membership.roles.includes("organization_owner");
          const disabled =
            !canManage || !csrfAvailable || pendingId === membership.id;
          return (
            <article className="resource-card" key={membership.id}>
              <div className="resource-card-heading">
                <div>
                  <h2>Subject {membership.identitySubjectId.slice(0, 8)}</h2>
                  <p>{membership.identitySubjectId}</p>
                </div>
                <span className="status-pill">{membership.status}</span>
              </div>
              <p>{membership.roles.map(roleLabel).join(" · ")}</p>
              {isOwner ? (
                <p className="inline-notice">
                  Owner lifecycle is protected and must be governed through the
                  platform owner-recovery path.
                </p>
              ) : (
                <>
                  {membership.status !== "revoked" ? (
                    <form
                      onSubmit={(event) => void replaceRoles(event, membership)}
                    >
                      <fieldset disabled={disabled}>
                        <legend>Built-in roles</legend>
                        <div className="checkbox-grid">
                          {assignableRoles.map((role) => (
                            <label className="checkbox-label" key={role}>
                              <input
                                defaultChecked={membership.roles.includes(role)}
                                name="roles"
                                type="checkbox"
                                value={role}
                              />
                              {roleLabel(role)}
                            </label>
                          ))}
                        </div>
                      </fieldset>
                      <div className="form-actions">
                        <button
                          className="button button-secondary"
                          type="submit"
                        >
                          Save roles
                        </button>
                      </div>
                    </form>
                  ) : null}
                  <div className="button-row">
                    {membership.status === "active" ? (
                      <button
                        className="button button-secondary"
                        disabled={disabled}
                        onClick={() => void transition(membership, "suspend")}
                        type="button"
                      >
                        Suspend
                      </button>
                    ) : null}
                    {membership.status === "suspended" ? (
                      <button
                        className="button button-secondary"
                        disabled={disabled}
                        onClick={() =>
                          void transition(membership, "reactivate")
                        }
                        type="button"
                      >
                        Reactivate
                      </button>
                    ) : null}
                    {membership.status !== "revoked" ? (
                      <button
                        className="button button-secondary"
                        disabled={disabled}
                        onClick={() => void transition(membership, "revoke")}
                        type="button"
                      >
                        Revoke
                      </button>
                    ) : null}
                  </div>
                </>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
