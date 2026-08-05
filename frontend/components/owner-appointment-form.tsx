"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { asRecord, readFirstString, unwrapPayload } from "@/lib/api/validation";

interface OwnerAppointmentResult {
  readonly id: string;
  readonly organizationId: string;
}

function parseOwnerAppointment(value: unknown): OwnerAppointmentResult {
  const record = asRecord(unwrapPayload(value));
  const id = record ? readFirstString(record, ["id"]) : undefined;
  const organizationId = record
    ? readFirstString(record, ["organization_id"])
    : undefined;
  if (!id || !organizationId) {
    throw new Error("The owner appointment response is not supported.");
  }
  return { id, organizationId };
}

export function OwnerAppointmentForm() {
  const [result, setResult] = useState<OwnerAppointmentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const csrfAvailable = useCsrfProtection();

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
        parseOwnerAppointment,
        {
          method: "POST",
          idempotencyKey: crypto.randomUUID(),
          body: {
            identity_subject_id: identitySubjectId,
            person_id: personId || null,
          },
        },
      );
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

  return (
    <form className="form-card" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label>
          Organization ID
          <input
            name="organizationId"
            type="text"
            required
            autoComplete="off"
          />
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
          Owner appointment is unavailable because this session did not provide
          CSRF protection.
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={!csrfAvailable || submitting}
        >
          {submitting ? "Appointing…" : "Appoint organization owner"}
        </button>
      </div>
    </form>
  );
}
