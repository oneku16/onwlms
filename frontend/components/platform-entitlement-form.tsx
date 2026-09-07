"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";

const featureCodes = [
  "academic",
  "moodle_integration",
  "ownid_sso",
  "mcp",
  "hr",
  "finance",
  "library",
  "dormitory",
  "advanced_analytics",
  "multiple_administrators",
  "custom_roles",
  "timetable_generation",
  "white_label",
] as const;

function asIso(value: FormDataEntryValue | null): string | null {
  const input = String(value ?? "").trim();
  return input ? new Date(input).toISOString() : null;
}

function successfulMutation(value: unknown): true {
  if (typeof value !== "object" || value === null) {
    throw new Error("The platform policy response is not supported.");
  }
  return true;
}

function MutationState({ message }: { readonly message: string | null }) {
  return message ? (
    <p className="inline-notice" role="status">
      {message}
    </p>
  ) : null;
}

export function SubscriptionAssignmentForm() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const csrfAvailable = useCsrfProtection();

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const organizationId = String(form.get("organizationId") ?? "").trim();
    try {
      await clientApiRequest(
        `/api/v1/platform/organizations/${encodeURIComponent(organizationId)}/subscription`,
        successfulMutation,
        {
          method: "PUT",
          body: {
            plan_id: String(form.get("planId") ?? "").trim(),
            status: String(form.get("status") ?? "active"),
            starts_at: asIso(form.get("startsAt")),
            ends_at: asIso(form.get("endsAt")),
          },
        },
      );
      setMessage(
        `Subscription policy updated for organization ${organizationId}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The subscription policy could not be updated.",
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
          <input name="organizationId" required autoComplete="off" />
        </label>
        <label>
          Plan ID
          <input name="planId" required autoComplete="off" />
        </label>
        <label>
          Status
          <select name="status" defaultValue="active">
            <option value="trialing">Trialing</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="canceled">Canceled</option>
          </select>
        </label>
        <label>
          Starts at
          <input name="startsAt" type="datetime-local" required />
        </label>
        <label>
          Ends at (optional)
          <input name="endsAt" type="datetime-local" />
        </label>
      </div>
      <MutationState message={message} />
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={!csrfAvailable || submitting}
        >
          {submitting ? "Saving…" : "Assign subscription"}
        </button>
      </div>
    </form>
  );
}

export function EntitlementOverrideForm() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const csrfAvailable = useCsrfProtection();

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const organizationId = String(form.get("organizationId") ?? "").trim();
    const enabled = form.get("enabled") === "on";
    const usageAmount = String(form.get("usageAmount") ?? "").trim();
    try {
      await clientApiRequest(
        `/api/v1/platform/organizations/${encodeURIComponent(organizationId)}/entitlements`,
        successfulMutation,
        {
          method: "PUT",
          body: {
            feature: String(form.get("feature") ?? ""),
            enabled,
            usage_limit:
              enabled && usageAmount
                ? {
                    amount: Number(usageAmount),
                    period: String(form.get("usagePeriod") ?? "absolute"),
                  }
                : null,
            expires_at: asIso(form.get("expiresAt")),
          },
        },
      );
      setMessage(
        `Feature override updated for organization ${organizationId}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The feature override could not be updated.",
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
          <input name="organizationId" required autoComplete="off" />
        </label>
        <label>
          Feature
          <select name="feature" defaultValue="mcp">
            {featureCodes.map((feature) => (
              <option key={feature} value={feature}>
                {feature.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input name="enabled" type="checkbox" defaultChecked />
          Enabled
        </label>
        <label>
          Usage amount (optional)
          <input name="usageAmount" type="number" min="1" step="1" />
        </label>
        <label>
          Usage period
          <select name="usagePeriod" defaultValue="absolute">
            <option value="month">Month</option>
            <option value="academic_term">Academic term</option>
            <option value="absolute">Absolute</option>
          </select>
        </label>
        <label>
          Expires at (optional)
          <input name="expiresAt" type="datetime-local" />
        </label>
      </div>
      <MutationState message={message} />
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={!csrfAvailable || submitting}
        >
          {submitting ? "Saving…" : "Set feature override"}
        </button>
      </div>
    </form>
  );
}
