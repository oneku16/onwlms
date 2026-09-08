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

export function DepartmentAdministration({
  canManage,
  faculties,
  initialDepartments,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly faculties: readonly ResourceSummary[];
  readonly initialDepartments: ResourceCollection;
  readonly organizationId: string;
}) {
  const [departments, setDepartments] = useState(initialDepartments);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createDepartment(
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
        "/api/v1/academics/departments",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            faculty_id: textValue(form.get("facultyId")),
            code: textValue(form.get("code")),
            name: textValue(form.get("name")),
          },
        },
      );
      setDepartments((current) => appendResource(current, created));
      setMessage(`Department “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The department could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {departments.items.length > 0 ? (
        <ResourceList collection={departments} />
      ) : (
        <EmptyState message="No departments are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createDepartment(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic structure</p>
            <h2>Create a department</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Faculty
            <select name="facultyId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a faculty"
                resources={faculties}
              />
            </select>
          </label>
          <label>
            Department code
            <input name="code" required maxLength={64} spellCheck={false} />
          </label>
          <label>
            Department name
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
              faculties.length === 0
            }
          >
            {submitting ? "Creating…" : "Create department"}
          </button>
        </div>
      </form>
    </div>
  );
}
