"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  featureCodes,
  parsePlan,
  usagePeriods,
  type PlanGrantView,
  type PlanView,
} from "@/lib/api/platform";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import {
  optionalTextValue,
  positiveIntegerValue,
  textValue,
} from "@/lib/forms";

const maximumGrants = 50;

function describeGrant(grant: PlanGrantView): string {
  return grant.usageLimit === null
    ? `${grant.feature} · unlimited`
    : `${grant.feature} · ${grant.usageLimit.amount.toLocaleString()} per ${grant.usageLimit.period}`;
}

export function PlanAdministration({
  initialPlans,
}: {
  readonly initialPlans: readonly PlanView[];
}) {
  const [plans, setPlans] = useState(initialPlans);
  const [grantKeys, setGrantKeys] = useState<readonly number[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function addGrant(): void {
    setGrantKeys((current) =>
      current.length >= maximumGrants
        ? current
        : [...current, Math.max(...current, -1) + 1],
    );
  }

  function removeGrant(key: number): void {
    setGrantKeys((current) => current.filter((candidate) => candidate !== key));
  }

  async function createPlan(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const grants: {
      feature: string;
      usage_limit: { amount: number; period: string } | null;
    }[] = [];
    for (const key of grantKeys) {
      const amountText = optionalTextValue(form.get(`grantAmount-${key}`));
      const amount =
        amountText === null ? null : positiveIntegerValue(amountText);
      if (amountText !== null && amount === null) {
        setError("Enter each usage amount as a positive whole number.");
        return;
      }
      grants.push({
        feature: textValue(form.get(`grantFeature-${key}`)),
        usage_limit:
          amount === null
            ? null
            : { amount, period: textValue(form.get(`grantPeriod-${key}`)) },
      });
    }
    setSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/platform/plans",
        parsePlan,
        {
          method: "POST",
          idempotencyKey: crypto.randomUUID(),
          body: {
            code: textValue(form.get("code")),
            display_name: textValue(form.get("displayName")),
            grants,
          },
        },
      );
      setPlans((current) => [...current, created]);
      setMessage(`Plan “${created.displayName}” was created.`);
      setGrantKeys([]);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The plan could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {plans.length === 0 ? (
        <EmptyState message="No plans are configured." />
      ) : (
        <section aria-labelledby="plans-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current records</p>
              <h2 id="plans-heading">
                {plans.length.toLocaleString()} plan
                {plans.length === 1 ? "" : "s"}
              </h2>
            </div>
          </div>
          <div className="resource-grid">
            {plans.map((plan) => (
              <article className="resource-card" key={plan.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>{plan.displayName}</h2>
                    <p>{plan.code}</p>
                  </div>
                  <span className="status-pill">
                    {plan.active ? "active" : "inactive"}
                  </span>
                </div>
                <dl className="resource-metadata">
                  <div>
                    <dt>Grants</dt>
                    <dd>
                      {plan.grants.length === 0
                        ? "No feature grants"
                        : plan.grants.map(describeGrant).join("; ")}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </section>
      )}
      <form className="form-card" onSubmit={(event) => void createPlan(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Product catalog</p>
            <h2>Create a plan</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Plan code
            <input name="code" required maxLength={80} spellCheck={false} />
          </label>
          <label>
            Display name
            <input name="displayName" required maxLength={120} />
          </label>
        </div>
        <fieldset disabled={submitting}>
          <legend>Feature grants (up to {maximumGrants})</legend>
          {grantKeys.map((key, index) => (
            <div className="form-grid" key={key}>
              <label>
                Grant {index + 1} feature
                <select name={`grantFeature-${key}`} required defaultValue="">
                  <option value="" disabled>
                    Select a feature
                  </option>
                  {featureCodes.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Grant {index + 1} usage amount (optional)
                <input
                  name={`grantAmount-${key}`}
                  type="number"
                  min="1"
                  step="1"
                />
                <small>Leave empty for an unlimited grant.</small>
              </label>
              <label>
                Grant {index + 1} usage period
                <select name={`grantPeriod-${key}`} defaultValue="absolute">
                  {usagePeriods.map((period) => (
                    <option key={period} value={period}>
                      {period}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-actions">
                <button
                  className="button button-secondary button-small"
                  type="button"
                  onClick={() => removeGrant(key)}
                >
                  Remove grant {index + 1}
                </button>
              </div>
            </div>
          ))}
          <div className="button-row">
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={grantKeys.length >= maximumGrants}
              onClick={addGrant}
            >
              Add feature grant
            </button>
          </div>
        </fieldset>
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
            Creation is unavailable because the session has no CSRF token.
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!csrfAvailable || submitting}
          >
            {submitting ? "Creating…" : "Create plan"}
          </button>
        </div>
      </form>
    </div>
  );
}
