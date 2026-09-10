"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { EmptyState } from "@/components/states";
import { parseAcademicYearSummary } from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { appendResource, type ResourceCollection } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { dateValue, textValue } from "@/lib/forms";

export function AcademicYearAdministration({
  canManage,
  initialAcademicYears,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly initialAcademicYears: ResourceCollection;
  readonly organizationId: string;
}) {
  const [academicYears, setAcademicYears] = useState(initialAcademicYears);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createAcademicYear(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const startsOn = dateValue(form.get("startsOn"));
    const endsOn = dateValue(form.get("endsOn"));
    if (!startsOn || !endsOn) {
      setError("Enter valid start and end dates.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/academic-years",
        parseAcademicYearSummary,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            name: textValue(form.get("name")),
            starts_on: startsOn,
            ends_on: endsOn,
          },
        },
      );
      setAcademicYears((current) => appendResource(current, created));
      setMessage(`Academic year “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The academic year could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {academicYears.items.length > 0 ? (
        <ResourceList collection={academicYears} />
      ) : (
        <EmptyState message="No academic years are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createAcademicYear(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic periods</p>
            <h2>Create an academic year</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Academic year name
            <input name="name" required maxLength={128} />
          </label>
          <label>
            Starts on
            <input name="startsOn" type="date" required />
          </label>
          <label>
            Ends on
            <input name="endsOn" type="date" required />
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage academic periods."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!canManage || !csrfAvailable || submitting}
          >
            {submitting ? "Creating…" : "Create academic year"}
          </button>
        </div>
      </form>
    </div>
  );
}
