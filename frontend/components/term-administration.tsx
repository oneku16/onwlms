"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { ResourceList } from "@/components/resource-list";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseCreatedResource,
  type ResourceCollection,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";

export function TermAdministration({
  canClose,
  initialTerms,
  organizationId,
}: {
  readonly canClose: boolean;
  readonly initialTerms: ResourceCollection;
  readonly organizationId: string;
}) {
  const [terms, setTerms] = useState(initialTerms);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function closeTerm(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    setError(null);
    const form = new FormData(event.currentTarget);
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
      event.currentTarget.reset();
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
      {terms.items.length > 0 ? <ResourceList collection={terms} /> : null}
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
