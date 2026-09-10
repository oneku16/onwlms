"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  appendResource,
  parseCreatedResource,
  type ResourceCollection,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { textValue } from "@/lib/forms";

export function CampusAdministration({
  canManage,
  initialCampuses,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly initialCampuses: ResourceCollection;
  readonly organizationId: string;
}) {
  const [campuses, setCampuses] = useState(initialCampuses);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createCampus(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const created = await clientApiRequest(
        "/api/v1/campuses",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            code: textValue(form.get("code")).toUpperCase(),
            name: textValue(form.get("name")),
          },
        },
      );
      setCampuses((current) => appendResource(current, created));
      setMessage(`Campus “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The campus could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {campuses.items.length > 0 ? (
        <ResourceList collection={campuses} />
      ) : (
        <EmptyState message="No campuses are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createCampus(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Organization structure</p>
            <h2>Create a campus</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Campus code
            <input
              name="code"
              required
              maxLength={32}
              pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,31}"
              autoCapitalize="characters"
              spellCheck={false}
            />
            <small>
              Letters, numbers, hyphens, and underscores; stored uppercase.
            </small>
          </label>
          <label>
            Campus name
            <input name="name" required maxLength={200} />
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage campuses."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!canManage || !csrfAvailable || submitting}
          >
            {submitting ? "Creating…" : "Create campus"}
          </button>
        </div>
      </form>
    </div>
  );
}
