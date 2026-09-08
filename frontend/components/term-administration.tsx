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
import { dateValue, isoFromDateTimeInput, textValue } from "@/lib/forms";

export function TermAdministration({
  academicYears,
  canClose,
  canManage,
  initialTerms,
  organizationId,
}: {
  readonly academicYears: readonly ResourceSummary[];
  readonly canClose: boolean;
  readonly canManage: boolean;
  readonly initialTerms: ResourceCollection;
  readonly organizationId: string;
}) {
  const [terms, setTerms] = useState(initialTerms);
  const [creating, setCreating] = useState(false);
  const [createMessage, setCreateMessage] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createTerm(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setCreateMessage(null);
    setCreateError(null);
    const startsOn = dateValue(form.get("startsOn"));
    const endsOn = dateValue(form.get("endsOn"));
    const enrollmentDeadline = isoFromDateTimeInput(
      form.get("enrollmentDeadline"),
    );
    if (!startsOn || !endsOn || !enrollmentDeadline) {
      setCreateError(
        "Enter valid start and end dates and an enrollment deadline.",
      );
      return;
    }
    setCreating(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/terms",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            academic_year_id: textValue(form.get("academicYearId")),
            name: textValue(form.get("name")),
            starts_on: startsOn,
            ends_on: endsOn,
            enrollment_deadline: enrollmentDeadline,
          },
        },
      );
      setTerms((current) => appendResource(current, created));
      setCreateMessage(`Term “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setCreateError(
        caught instanceof ApiError
          ? caught.message
          : "The academic term could not be created.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function closeTerm(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    setSubmitting(true);
    setMessage(null);
    setError(null);
    const form = new FormData(formElement);
    const termId = String(form.get("termId") ?? "").trim();
    try {
      const closed = await clientApiRequest(
        `/api/v1/academics/terms/${encodeURIComponent(termId)}/close`,
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          body: { explanation: String(form.get("explanation") ?? "").trim() },
        },
      );
      setTerms((current) => ({
        total: current.total,
        items: current.items.map((term) =>
          term.id === closed.id ? { ...closed, status: "closed" } : term,
        ),
      }));
      setMessage(`“${closed.title}” is now closed.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The academic term could not be closed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {terms.items.length > 0 ? (
        <ResourceList collection={terms} />
      ) : (
        <EmptyState message="No terms and semesters are available." />
      )}
      <form className="form-card" onSubmit={(event) => void createTerm(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic periods</p>
            <h2>Create a term</h2>
          </div>
        </div>
        <div className="form-grid">
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
            Term name
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
          <label className="form-span">
            Enrollment deadline
            <input name="enrollmentDeadline" type="datetime-local" required />
            <small>
              Entered in your browser timezone and stored as a UTC instant.
            </small>
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={createError}
          message={createMessage}
          permissionNotice="Your current membership cannot manage academic periods."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              creating ||
              academicYears.length === 0
            }
          >
            {creating ? "Creating…" : "Create term"}
          </button>
        </div>
      </form>
      <form className="form-card" onSubmit={(event) => void closeTerm(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Official lifecycle</p>
            <h2>Close an academic term</h2>
          </div>
        </div>
        <p className="inline-notice">
          Closure is one-way. Later official-grade changes require a separate
          explanation and closed-term revision permission.
        </p>
        <div className="form-grid">
          <label>
            Term
            <select name="termId" required defaultValue="">
              <option value="" disabled>
                Select an open term
              </option>
              {terms.items
                .filter((term) => term.status !== "closed")
                .map((term) => (
                  <option key={term.id} value={term.id}>
                    {term.title}
                  </option>
                ))}
            </select>
          </label>
          <label className="form-span">
            Closure explanation
            <textarea
              name="explanation"
              required
              minLength={10}
              maxLength={500}
              rows={5}
            />
            <small>
              This reason is retained as privacy-minimized audit evidence.
            </small>
          </label>
        </div>
        {error ? (
          <p className="inline-alert" role="alert">
            {error}
          </p>
        ) : null}
        {message ? (
          <p className="inline-success" role="status">
            {message}
          </p>
        ) : null}
        {!canClose ? (
          <p className="inline-notice">
            Your current membership cannot close academic terms.
          </p>
        ) : !csrfAvailable ? (
          <p className="inline-notice">
            Closure is unavailable because the session has no CSRF token.
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!canClose || !csrfAvailable || submitting}
          >
            {submitting ? "Closing term…" : "Close term"}
          </button>
        </div>
      </form>
    </div>
  );
}
