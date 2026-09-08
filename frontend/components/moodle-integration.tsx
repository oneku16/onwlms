"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseMoodleStatus,
  type MoodleStatusView,
} from "@/lib/api/integrations";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { textValue } from "@/lib/forms";

const minimumSecretLength = 32;

function isHttpsUrl(value: string): boolean {
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

function formatInstant(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

export function MoodleIntegration({
  canConfigure,
  initialStatus,
  organizationId,
}: {
  readonly canConfigure: boolean;
  readonly initialStatus: MoodleStatusView;
  readonly organizationId: string;
}) {
  const [status, setStatus] = useState(initialStatus);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingSecret, setSavingSecret] = useState(false);
  const [secretMessage, setSecretMessage] = useState<string | null>(null);
  const [secretError, setSecretError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function saveGradeEventSecret(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const secret = String(new FormData(formElement).get("secret") ?? "");
    setSecretMessage(null);
    setSecretError(null);
    if (secret.length < minimumSecretLength || secret.trim() !== secret) {
      setSecretError(
        `Use at least ${minimumSecretLength} characters without leading or trailing spaces.`,
      );
      return;
    }
    setSavingSecret(true);
    try {
      const updated = await clientApiRequest(
        "/api/v1/integrations/moodle/grade-event-secret",
        parseMoodleStatus,
        { method: "PUT", organizationId, body: { secret } },
      );
      setStatus(updated);
      setSecretMessage(
        "Grade-event secret saved. It is stored encrypted and is never displayed.",
      );
      formElement.reset();
    } catch (caught) {
      setSecretError(
        caught instanceof ApiError
          ? caught.message
          : "The grade-event secret could not be saved.",
      );
    } finally {
      setSavingSecret(false);
    }
  }

  async function configure(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const baseUrl = textValue(form.get("baseUrl"));
    if (!isHttpsUrl(baseUrl)) {
      setError("Enter the Moodle base URL as an https:// address.");
      return;
    }
    setSubmitting(true);
    try {
      const updated = await clientApiRequest(
        "/api/v1/integrations/moodle/configuration",
        parseMoodleStatus,
        {
          method: "PUT",
          organizationId,
          body: { base_url: baseUrl, token: String(form.get("token") ?? "") },
        },
      );
      setStatus(updated);
      setMessage(
        "Moodle configuration saved. The token is stored encrypted and is never displayed.",
      );
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The Moodle configuration could not be saved.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      <form className="form-card" onSubmit={(event) => void configure(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Learning delivery</p>
            <h2>Configure Moodle connectivity</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Moodle base URL
            <input
              name="baseUrl"
              type="url"
              required
              minLength={12}
              maxLength={500}
              inputMode="url"
              spellCheck={false}
              defaultValue={status.baseUrl ?? ""}
            />
            <small>Only https:// endpoints are accepted.</small>
          </label>
          <label>
            Web service token
            <input
              name="token"
              type="password"
              required
              autoComplete="new-password"
            />
            <small>Never shown again after saving.</small>
          </label>
        </div>
        <FormFeedback
          canMutate={canConfigure}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot configure integrations."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!canConfigure || !csrfAvailable || submitting}
          >
            {submitting ? "Saving…" : "Save Moodle configuration"}
          </button>
        </div>
      </form>
      <form
        className="form-card"
        onSubmit={(event) => void saveGradeEventSecret(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Signed grade events</p>
            <h2>Configure the grade-event secret</h2>
          </div>
        </div>
        <p className="inline-notice">
          A Moodle-side sender signs each grade event with this shared secret.
          Events only create pending evidence; an authorized person still
          accepts or rejects each one.
        </p>
        <div className="form-grid">
          <label>
            Grade-event signing secret
            <input
              name="secret"
              type="password"
              required
              minLength={minimumSecretLength}
              maxLength={256}
              autoComplete="new-password"
            />
            <small>
              At least {minimumSecretLength} characters. Saving replaces any
              previous secret immediately.
            </small>
          </label>
        </div>
        <FormFeedback
          canMutate={canConfigure}
          csrfAvailable={csrfAvailable}
          error={secretError}
          message={secretMessage}
          permissionNotice="Your current membership cannot configure integrations."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!canConfigure || !csrfAvailable || savingSecret}
          >
            {savingSecret ? "Saving…" : "Save grade-event secret"}
          </button>
        </div>
      </form>
      <section className="form-card" aria-labelledby="moodle-status-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Safe status evidence</p>
            <h2 id="moodle-status-heading">Moodle integration</h2>
          </div>
          <span className="status-pill">{status.status}</span>
        </div>
        <dl className="resource-metadata">
          <div>
            <dt>Configured</dt>
            <dd>{status.configured ? "Yes" : "No"}</dd>
          </div>
          <div>
            <dt>Base URL</dt>
            <dd>{status.baseUrl ?? "Not configured"}</dd>
          </div>
          <div>
            <dt>Last success</dt>
            <dd>
              {status.lastSuccessAt
                ? formatInstant(status.lastSuccessAt)
                : "No successful check yet"}
            </dd>
          </div>
          <div>
            <dt>Grade events</dt>
            <dd>
              {status.gradeEventsConfigured
                ? "Signing secret configured"
                : "No signing secret"}
            </dd>
          </div>
          <div>
            <dt>Last error code</dt>
            <dd>{status.lastErrorCode ?? "None"}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
