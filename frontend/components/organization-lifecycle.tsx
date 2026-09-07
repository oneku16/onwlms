"use client";

import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseCreatedResource,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";

export function OrganizationLifecycle({
  initialOrganizations,
}: {
  readonly initialOrganizations: readonly ResourceSummary[];
}) {
  const [organizations, setOrganizations] = useState(initialOrganizations);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function transition(
    organization: ResourceSummary,
    action: "suspend" | "reactivate",
  ): Promise<void> {
    if (
      action === "suspend" &&
      !window.confirm(
        "Suspend this organization? Active tenant memberships will immediately lose ordinary access.",
      )
    ) {
      return;
    }
    setError(null);
    setPendingId(organization.id);
    try {
      const updated = await clientApiRequest(
        `/api/v1/platform/organizations/${encodeURIComponent(organization.id)}/${action}`,
        parseCreatedResource,
        { method: "POST" },
      );
      setOrganizations((current) =>
        current.map((candidate) =>
          candidate.id === updated.id ? updated : candidate,
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The organization lifecycle change could not be saved.",
      );
    } finally {
      setPendingId(null);
    }
  }

  return (
    <section aria-labelledby="organization-lifecycle-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Tenant governance</p>
          <h2 id="organization-lifecycle-heading">Organizations</h2>
        </div>
      </div>
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      <div className="resource-grid">
        {organizations.map((organization) => (
          <article className="resource-card" key={organization.id}>
            <div className="resource-card-heading">
              <div>
                <h2>{organization.title}</h2>
                {organization.subtitle ? <p>{organization.subtitle}</p> : null}
              </div>
              <span className="status-pill">
                {organization.status ?? "unknown"}
              </span>
            </div>
            <div className="button-row">
              {organization.status === "active" ? (
                <button
                  className="button button-secondary"
                  disabled={!csrfAvailable || pendingId !== null}
                  onClick={() => void transition(organization, "suspend")}
                  type="button"
                >
                  Suspend
                </button>
              ) : null}
              {organization.status === "suspended" ? (
                <button
                  className="button button-secondary"
                  disabled={!csrfAvailable || pendingId !== null}
                  onClick={() => void transition(organization, "reactivate")}
                  type="button"
                >
                  Reactivate
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
