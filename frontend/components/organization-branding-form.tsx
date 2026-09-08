"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  organizationEducationModes,
  parseOrganizationConfiguration,
  type OrganizationConfigurationView,
  type OrganizationEducationMode,
} from "@/lib/api/organization";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { optionalTextValue, textValue } from "@/lib/forms";

const educationModeLabels: Readonly<Record<OrganizationEducationMode, string>> =
  {
    fixed: "Fixed curriculum",
    flexible: "Flexible curriculum",
    hybrid: "Hybrid curriculum",
  };

export function OrganizationBrandingForm({
  canConfigure,
  initialOrganization,
  organizationId,
}: {
  readonly canConfigure: boolean;
  readonly initialOrganization: OrganizationConfigurationView;
  readonly organizationId: string;
}) {
  const [organization, setOrganization] = useState(initialOrganization);
  /** Increments after each successful save so the form remounts with saved defaults. */
  const [savedRevision, setSavedRevision] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();
  const logo = organization.branding.logo;

  async function save(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setMessage(null);
    setError(null);
    if (logo && form.get("clearLogo") !== "on") {
      setError(
        "Confirm that the stored logo metadata will be cleared before saving.",
      );
      return;
    }
    const customDomain = optionalTextValue(form.get("customDomain"));
    setSubmitting(true);
    try {
      const saved = await clientApiRequest(
        "/api/v1/organization",
        parseOrganizationConfiguration,
        {
          method: "PUT",
          organizationId,
          body: {
            branding: {
              display_name: textValue(form.get("displayName")),
              primary_color: textValue(form.get("primaryColor")),
              secondary_color: textValue(form.get("secondaryColor")),
              logo: null,
            },
            configuration: {
              locale: textValue(form.get("locale")),
              timezone: textValue(form.get("timezone")),
              education_mode: textValue(form.get("educationMode")),
              custom_domain:
                customDomain === null
                  ? null
                  : { domain: customDomain, verification_status: "pending" },
              ownid_tenant_reference: optionalTextValue(
                form.get("ownidTenantReference"),
              ),
              ownid_client_reference: optionalTextValue(
                form.get("ownidClientReference"),
              ),
            },
          },
        },
      );
      setOrganization(saved);
      setSavedRevision((current) => current + 1);
      setMessage("Organization configuration saved.");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The organization configuration could not be saved.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      <section className="form-card" aria-labelledby="organization-summary">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Tenant record</p>
            <h2 id="organization-summary">
              {organization.branding.displayName}
            </h2>
          </div>
          <span className="status-pill">{organization.status}</span>
        </div>
        <dl className="resource-metadata">
          <div>
            <dt>Slug</dt>
            <dd>{organization.slug}</dd>
          </div>
          <div>
            <dt>Type</dt>
            <dd>{organization.organizationType}</dd>
          </div>
          <div>
            <dt>Logo</dt>
            <dd>
              {logo
                ? `${logo.fileName} · ${logo.contentType} · ${logo.sizeBytes.toLocaleString()} bytes`
                : "No logo metadata"}
            </dd>
          </div>
          <div>
            <dt>Custom domain</dt>
            <dd>
              {organization.configuration.customDomain
                ? `${organization.configuration.customDomain.domain} · ${organization.configuration.customDomain.verificationStatus}`
                : "Not configured"}
            </dd>
          </div>
        </dl>
      </section>
      <form
        className="form-card"
        key={`${organization.id}:${savedRevision}`}
        onSubmit={(event) => void save(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Branding and configuration</p>
            <h2>Replace the organization configuration</h2>
          </div>
        </div>
        <p className="inline-notice">
          Saving replaces the full non-secret configuration. Logo uploads are
          not available in this release.
        </p>
        <div className="form-grid">
          <label className="form-span">
            Display name
            <input
              name="displayName"
              required
              maxLength={200}
              defaultValue={organization.branding.displayName}
            />
          </label>
          <label>
            Primary brand color
            <input
              name="primaryColor"
              type="color"
              defaultValue={organization.branding.primaryColor.toLowerCase()}
            />
          </label>
          <label>
            Secondary brand color
            <input
              name="secondaryColor"
              type="color"
              defaultValue={organization.branding.secondaryColor.toLowerCase()}
            />
          </label>
          <label>
            Locale
            <input
              name="locale"
              required
              maxLength={16}
              defaultValue={organization.configuration.locale}
            />
          </label>
          <label>
            Timezone
            <input
              name="timezone"
              required
              maxLength={64}
              defaultValue={organization.configuration.timezone}
            />
          </label>
          <label>
            Education mode
            <select
              name="educationMode"
              required
              defaultValue={organization.configuration.educationMode}
            >
              {organizationEducationModes.map((mode) => (
                <option key={mode} value={mode}>
                  {educationModeLabels[mode]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Custom domain (optional)
            <input
              name="customDomain"
              maxLength={253}
              autoCapitalize="none"
              spellCheck={false}
              defaultValue={
                organization.configuration.customDomain?.domain ?? ""
              }
            />
            <small>A saved domain always starts in pending verification.</small>
          </label>
          <label>
            OwnID tenant reference (optional)
            <input
              name="ownidTenantReference"
              maxLength={255}
              autoComplete="off"
              defaultValue={
                organization.configuration.ownidTenantReference ?? ""
              }
            />
          </label>
          <label>
            OwnID client reference (optional)
            <input
              name="ownidClientReference"
              maxLength={255}
              autoComplete="off"
              defaultValue={
                organization.configuration.ownidClientReference ?? ""
              }
            />
          </label>
          {logo ? (
            <label className="checkbox-label form-span">
              <input name="clearLogo" type="checkbox" />
              Clear the stored logo metadata when saving
            </label>
          ) : null}
        </div>
        {logo ? (
          <p className="inline-notice">
            The organization API does not return the logo storage key, so this
            form cannot resubmit the existing logo. Saving clears its metadata.
          </p>
        ) : null}
        <FormFeedback
          canMutate={canConfigure}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot configure the organization."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!canConfigure || !csrfAvailable || submitting}
          >
            {submitting ? "Saving…" : "Save configuration"}
          </button>
        </div>
      </form>
    </div>
  );
}
