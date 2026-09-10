"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  featureCodes,
  parseFeature,
  type FeatureView,
} from "@/lib/api/platform";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { textValue } from "@/lib/forms";

export function FeatureAdministration({
  initialFeatures,
}: {
  readonly initialFeatures: readonly FeatureView[];
}) {
  const [features, setFeatures] = useState(initialFeatures);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();
  const registeredCodes = new Set(features.map((feature) => feature.code));
  const availableCodes = featureCodes.filter(
    (code) => !registeredCodes.has(code),
  );

  async function createFeature(
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
        "/api/v1/platform/features",
        parseFeature,
        {
          method: "POST",
          idempotencyKey: crypto.randomUUID(),
          body: {
            code: textValue(form.get("code")),
            display_name: textValue(form.get("displayName")),
          },
        },
      );
      setFeatures((current) => [...current, created]);
      setMessage(`Feature “${created.displayName}” was registered.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The feature could not be registered.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {features.length === 0 ? (
        <EmptyState message="No features are registered." />
      ) : (
        <section aria-labelledby="features-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current records</p>
              <h2 id="features-heading">
                {features.length.toLocaleString()} feature
                {features.length === 1 ? "" : "s"}
              </h2>
            </div>
          </div>
          <div className="resource-grid">
            {features.map((feature) => (
              <article className="resource-card" key={feature.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>{feature.displayName}</h2>
                    <p>{feature.code}</p>
                  </div>
                  <span className="status-pill">
                    {feature.baseIncluded
                      ? "base included"
                      : "plan or override"}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createFeature(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Product catalog</p>
            <h2>Register a feature</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Feature code
            <select name="code" required defaultValue="">
              <option value="" disabled>
                {availableCodes.length === 0
                  ? "Every supported feature code is registered"
                  : "Select a feature code"}
              </option>
              {availableCodes.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
          <label>
            Display name
            <input name="displayName" required maxLength={120} />
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
        {!csrfAvailable ? (
          <p className="inline-notice">
            Registration is unavailable because the session has no CSRF token.
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !csrfAvailable || submitting || availableCodes.length === 0
            }
          >
            {submitting ? "Registering…" : "Register feature"}
          </button>
        </div>
      </form>
    </div>
  );
}
