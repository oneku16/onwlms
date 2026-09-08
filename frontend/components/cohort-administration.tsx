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

export function CohortAdministration({
  academicYears,
  canManage,
  initialCohorts,
  organizationId,
  programs,
}: {
  readonly academicYears: readonly ResourceSummary[];
  readonly canManage: boolean;
  readonly initialCohorts: ResourceCollection;
  readonly organizationId: string;
  readonly programs: readonly ResourceSummary[];
}) {
  const [cohorts, setCohorts] = useState(initialCohorts);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createCohort(
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
        "/api/v1/academics/cohorts",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            program_id: textValue(form.get("programId")),
            academic_year_id: textValue(form.get("academicYearId")),
            code: textValue(form.get("code")),
            name: textValue(form.get("name")),
          },
        },
      );
      setCohorts((current) => appendResource(current, created));
      setMessage(`Cohort “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The cohort could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {cohorts.items.length > 0 ? (
        <ResourceList collection={cohorts} />
      ) : (
        <EmptyState message="No groups and cohorts are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createCohort(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Student groups</p>
            <h2>Create a cohort</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Program
            <select name="programId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a program"
                resources={programs}
              />
            </select>
          </label>
          <label>
            Academic year
            <select name="academicYearId" required defaultValue="">
              <ResourceOptions
                placeholder="Select an academic year"
                resources={academicYears}
              />
            </select>
          </label>
          <label>
            Cohort code
            <input name="code" required maxLength={64} spellCheck={false} />
          </label>
          <label>
            Cohort name
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
              programs.length === 0 ||
              academicYears.length === 0
            }
          >
            {submitting ? "Creating…" : "Create cohort"}
          </button>
        </div>
      </form>
    </div>
  );
}
