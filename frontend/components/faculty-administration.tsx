"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  appendResource,
  parseCreatedResource,
  type ResourceCollection,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { textValue } from "@/lib/forms";

export function FacultyAdministration({
  campuses,
  canManage,
  initialFaculties,
  organizationId,
}: {
  readonly campuses: readonly ResourceSummary[];
  readonly canManage: boolean;
  readonly initialFaculties: ResourceCollection;
  readonly organizationId: string;
}) {
  const [faculties, setFaculties] = useState(initialFaculties);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createFaculty(
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
        "/api/v1/academics/faculties",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            campus_id: textValue(form.get("campusId")),
            code: textValue(form.get("code")),
            name: textValue(form.get("name")),
          },
        },
      );
      setFaculties((current) => appendResource(current, created));
      setMessage(`Faculty “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The faculty could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {faculties.items.length > 0 ? (
        <ResourceList collection={faculties} />
      ) : (
        <EmptyState message="No faculties are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createFaculty(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic structure</p>
            <h2>Create a faculty</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Campus
            <select name="campusId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a campus"
                resources={campuses}
              />
            </select>
          </label>
          <label>
            Faculty code
            <input name="code" required maxLength={64} spellCheck={false} />
          </label>
          <label>
            Faculty name
            <input name="name" required maxLength={255} />
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage the academic structure."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              submitting ||
              campuses.length === 0
            }
          >
            {submitting ? "Creating…" : "Create faculty"}
          </button>
        </div>
      </form>
    </div>
  );
}
