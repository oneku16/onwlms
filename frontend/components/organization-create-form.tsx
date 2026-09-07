"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import Link from "next/link";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseCreatedResource,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";

export function OrganizationCreateForm() {
  const [created, setCreated] = useState<ResourceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const csrfAvailable = useCsrfProtection();

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const displayName = String(form.get("displayName") ?? "").trim();
    const slug = String(form.get("slug") ?? "")
      .trim()
      .toLowerCase();
    const organizationType = String(form.get("organizationType") ?? "");
    const locale = String(form.get("locale") ?? "").trim();
    const timezone = String(form.get("timezone") ?? "").trim();
    const educationMode = String(form.get("educationMode") ?? "fixed");
    const primaryColor = String(form.get("primaryColor") ?? "#1d4ed8");
    const secondaryColor = String(form.get("secondaryColor") ?? "#0f172a");

    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
      setError("Slug must use lowercase letters, numbers, and single hyphens.");
      setSubmitting(false);
      return;
    }

    try {
      const resource = await clientApiRequest(
        "/api/v1/platform/organizations",
        parseCreatedResource,
        {
          method: "POST",
          idempotencyKey: crypto.randomUUID(),
          body: {
            slug,
            organization_type: organizationType,
            branding: {
              display_name: displayName,
              primary_color: primaryColor,
              secondary_color: secondaryColor,
            },
            configuration: {
              locale,
              timezone,
              education_mode: educationMode,
            },
          },
        },
      );
      setCreated(resource);
      event.currentTarget.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The organization could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
    return (
      <section className="state-panel state-success" role="status">
        <p className="state-kicker">Organization created</p>
        <h2>{created.title}</h2>
        <p>The backend accepted the new isolated tenant record.</p>
        <div className="button-row">
          <button
            className="button button-secondary"
            type="button"
            onClick={() => setCreated(null)}
          >
            Create another
          </button>
          <Link className="button" href="/platform/organizations">
            View organizations
          </Link>
        </div>
      </section>
    );
  }

  return (
    <form className="form-card" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label>
          Display name
          <input
            name="displayName"
            required
            maxLength={160}
            autoComplete="organization"
          />
        </label>
        <label>
          Organization slug
          <input
            name="slug"
            required
            maxLength={63}
            pattern="[a-z0-9]+(-[a-z0-9]+)*"
            autoCapitalize="none"
            spellCheck={false}
          />
          <small>Lowercase letters, numbers, and hyphens.</small>
        </label>
        <label>
          Organization type
          <select name="organizationType" required defaultValue="">
            <option value="" disabled>
              Select a type
            </option>
            <option value="school">School</option>
            <option value="college">College</option>
            <option value="university">University</option>
            <option value="institute">Institute</option>
          </select>
        </label>
        <label>
          Locale
          <input name="locale" required defaultValue="en" maxLength={35} />
        </label>
        <label>
          Timezone
          <input
            name="timezone"
            required
            defaultValue="Asia/Bishkek"
            maxLength={64}
          />
        </label>
        <label>
          Education mode
          <select name="educationMode" defaultValue="fixed">
            <option value="fixed">Fixed curriculum</option>
            <option value="flexible">Flexible curriculum</option>
            <option value="hybrid">Hybrid curriculum</option>
          </select>
        </label>
        <label>
          Primary brand color
          <input name="primaryColor" type="color" defaultValue="#1d4ed8" />
        </label>
        <label>
          Secondary brand color
          <input name="secondaryColor" type="color" defaultValue="#0f172a" />
        </label>
      </div>
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      {!csrfAvailable ? (
        <p className="inline-notice">
          Creation is unavailable because the authenticated session did not
          provide CSRF protection.
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={!csrfAvailable || submitting}
        >
          {submitting ? "Creating…" : "Create organization"}
        </button>
      </div>
    </form>
  );
}
