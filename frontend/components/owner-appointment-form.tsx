"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import {
  parseOwnerLifecycle,
  type OwnerLifecycleView,
} from "@/lib/api/administration";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import type { ResourceSummary } from "@/lib/api/resources";

export function OwnerAppointmentForm({
  initialOwners,
  organizations,
}: {
  readonly initialOwners: readonly OwnerLifecycleView[];
  readonly organizations: readonly ResourceSummary[];
}) {
  const [owners, setOwners] = useState(initialOwners);
  const [result, setResult] = useState<OwnerLifecycleView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingOwnerId, setPendingOwnerId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const csrfAvailable = useCsrfProtection();

  function storeOwner(updated: OwnerLifecycleView): void {
    setOwners((current) => {
      const exists = current.some((owner) => owner.id === updated.id);
      return exists
        ? current.map((owner) => (owner.id === updated.id ? updated : owner))
        : [...current, updated];
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const organizationId = String(form.get("organizationId") ?? "").trim();
    const identitySubjectId = String(
      form.get("identitySubjectId") ?? "",
    ).trim();
    const personId = String(form.get("personId") ?? "").trim();
    try {
      const appointment = await clientApiRequest(
        `/api/v1/platform/organizations/${encodeURIComponent(organizationId)}/owner`,
        parseOwnerLifecycle,
        {
          method: "POST",
          idempotencyKey: crypto.randomUUID(),
          body: {
            identity_subject_id: identitySubjectId,
            person_id: personId || null,
          },
        },
      );
      storeOwner(appointment);
      setResult(appointment);
      event.currentTarget.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The organization owner could not be appointed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function transitionOwner(
    owner: OwnerLifecycleView,
    action: "suspend" | "revoke",
  ): Promise<void> {
    const warning =
      action === "revoke"
        ? "Permanently revoke this owner membership? It cannot be reactivated."
        : "Suspend this owner membership? Another active owner must remain.";
    if (!window.confirm(warning)) {
      return;
    }
    setError(null);
    setPendingOwnerId(owner.id);
    try {
      storeOwner(
        await clientApiRequest(
          `/api/v1/platform/organizations/${encodeURIComponent(owner.organizationId)}/owners/${encodeURIComponent(owner.id)}/${action}`,
          parseOwnerLifecycle,
          { method: "POST" },
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The organization-owner lifecycle change could not be saved.",
      );
    } finally {
      setPendingOwnerId(null);
    }
  }

  function organizationTitle(organizationId: string): string {
    return (
      organizations.find((organization) => organization.id === organizationId)
        ?.title ?? `Organization ${organizationId.slice(0, 8)}`
    );
  }

  return (
    <>
      <form className="form-card" onSubmit={(event) => void submit(event)}>
        <div className="form-grid">
          <label>
            Organization
            <select name="organizationId" required defaultValue="">
              <option value="" disabled>
                Select an organization
              </option>
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            OwnSIS identity subject ID
            <input
              name="identitySubjectId"
              type="text"
              required
              autoComplete="off"
            />
            <small>This is the internal subject UUID linked to OwnID.</small>
          </label>
          <label>
            Existing person ID (optional)
            <input name="personId" type="text" autoComplete="off" />
          </label>
        </div>
        {result ? (
          <p className="inline-notice" role="status">
            Owner membership {result.id} is active for organization{" "}
            {result.organizationId}.
          </p>
        ) : null}
        {error ? (
          <p className="inline-alert" role="alert">
            {error}
          </p>
        ) : null}
        {!csrfAvailable ? (
          <p className="inline-notice">
            Owner governance is unavailable because this session did not provide
            CSRF protection.
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !csrfAvailable || submitting || organizations.length === 0
            }
          >
            {submitting ? "Appointing…" : "Appoint organization owner"}
          </button>
        </div>
      </form>
      <section aria-labelledby="organization-owners-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Tenant access recovery</p>
            <h2 id="organization-owners-heading">Owner memberships</h2>
            <p>
              Suspend or permanently revoke an owner only after another active
              owner has been established.
            </p>
          </div>
        </div>
        {owners.length === 0 ? (
          <p className="empty-state">No organization owners are recorded.</p>
        ) : (
          <div className="resource-grid">
            {owners.map((owner) => {
              const disabled =
                !csrfAvailable ||
                pendingOwnerId !== null ||
                owner.status === "revoked";
              return (
                <article className="resource-card" key={owner.id}>
                  <div className="resource-card-heading">
                    <div>
                      <h2>{organizationTitle(owner.organizationId)}</h2>
                      <p>Owner membership {owner.id}</p>
                    </div>
                    <span className="status-pill">{owner.status}</span>
                  </div>
                  {owner.status === "active" ? (
                    <div className="button-row">
                      <button
                        className="button button-secondary"
                        disabled={disabled}
                        onClick={() => void transitionOwner(owner, "suspend")}
                        type="button"
                      >
                        Suspend
                      </button>
                      <button
                        className="button button-secondary"
                        disabled={disabled}
                        onClick={() => void transitionOwner(owner, "revoke")}
                        type="button"
                      >
                        Revoke permanently
                      </button>
                    </div>
                  ) : null}
                  {owner.status === "suspended" ? (
                    <div className="button-row">
                      <button
                        className="button button-secondary"
                        disabled={disabled}
                        onClick={() => void transitionOwner(owner, "revoke")}
                        type="button"
                      >
                        Revoke permanently
                      </button>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
