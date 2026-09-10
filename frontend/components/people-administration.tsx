"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { contactKinds, parseProfile, profileKinds } from "@/lib/api/people";
import {
  appendResource,
  parseCreatedResource,
  resourceTitle,
  type ResourceCollection,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { dateValue, optionalTextValue, textValue } from "@/lib/forms";

const maximumContacts = 20;

export function PeopleAdministration({
  canManage,
  initialPeople,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly initialPeople: ResourceCollection;
  readonly organizationId: string;
}) {
  const [people, setPeople] = useState(initialPeople);
  const [contactKeys, setContactKeys] = useState<readonly number[]>([]);
  const [creating, setCreating] = useState(false);
  const [createMessage, setCreateMessage] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [addingProfile, setAddingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function addContact(): void {
    setContactKeys((current) =>
      current.length >= maximumContacts
        ? current
        : [...current, Math.max(...current, -1) + 1],
    );
  }

  function removeContact(key: number): void {
    setContactKeys((current) =>
      current.filter((candidate) => candidate !== key),
    );
  }

  async function createPerson(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setCreateMessage(null);
    setCreateError(null);
    const dateOfBirthText = optionalTextValue(form.get("dateOfBirth"));
    const dateOfBirth =
      dateOfBirthText === null ? null : dateValue(dateOfBirthText);
    if (dateOfBirthText !== null && dateOfBirth === null) {
      setCreateError("Enter the date of birth as a calendar date.");
      return;
    }
    const contacts: {
      kind: string;
      value: string;
      label: string | null;
      is_primary: boolean;
      whatsapp_capable: boolean;
    }[] = [];
    for (const key of contactKeys) {
      const value = textValue(form.get(`contactValue-${key}`));
      if (!value) {
        setCreateError("Enter a value for every contact method.");
        return;
      }
      contacts.push({
        kind: textValue(form.get(`contactKind-${key}`)),
        value,
        label: optionalTextValue(form.get(`contactLabel-${key}`)),
        is_primary: form.get(`contactPrimary-${key}`) === "on",
        whatsapp_capable: form.get(`contactWhatsapp-${key}`) === "on",
      });
    }
    setCreating(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/people",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            given_name: textValue(form.get("givenName")),
            family_name: textValue(form.get("familyName")),
            preferred_name: optionalTextValue(form.get("preferredName")),
            date_of_birth: dateOfBirth,
            national_identifier: optionalTextValue(
              form.get("nationalIdentifier"),
            ),
            contacts,
          },
        },
      );
      setPeople((current) => appendResource(current, created));
      setCreateMessage(`Person “${created.title}” was created.`);
      setContactKeys([]);
      formElement.reset();
    } catch (caught) {
      setCreateError(
        caught instanceof ApiError
          ? caught.message
          : "The person could not be created.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function addProfile(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const personId = textValue(form.get("personId"));
    setAddingProfile(true);
    setProfileMessage(null);
    setProfileError(null);
    try {
      const profile = await clientApiRequest(
        `/api/v1/people/${encodeURIComponent(personId)}/profiles`,
        parseProfile,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            kind: textValue(form.get("kind")),
            reference_number: optionalTextValue(form.get("referenceNumber")),
            title: optionalTextValue(form.get("title")),
          },
        },
      );
      setProfileMessage(
        `A ${profile.kind} profile was added for ${resourceTitle(people.items, profile.personId, "Person")}.`,
      );
      formElement.reset();
    } catch (caught) {
      setProfileError(
        caught instanceof ApiError
          ? caught.message
          : "The profile could not be added.",
      );
    } finally {
      setAddingProfile(false);
    }
  }

  const mutationDisabled = !canManage || !csrfAvailable;

  return (
    <div className="notification-layout">
      {people.items.length > 0 ? (
        <ResourceList collection={people} />
      ) : (
        <EmptyState message="No people are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createPerson(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">People directory</p>
            <h2>Create a person</h2>
          </div>
        </div>
        <p className="inline-notice">
          Identifiers and contact values are stored privately and are never
          displayed again after saving.
        </p>
        <div className="form-grid">
          <label>
            Given name
            <input name="givenName" required maxLength={120} />
          </label>
          <label>
            Family name
            <input name="familyName" required maxLength={120} />
          </label>
          <label>
            Preferred name (optional)
            <input name="preferredName" maxLength={120} />
          </label>
          <label>
            Date of birth (optional)
            <input name="dateOfBirth" type="date" />
          </label>
          <label className="form-span">
            National identifier (optional)
            <input
              name="nationalIdentifier"
              maxLength={64}
              autoComplete="off"
              spellCheck={false}
            />
          </label>
        </div>
        <fieldset disabled={creating}>
          <legend>Contact methods (optional, up to {maximumContacts})</legend>
          {contactKeys.map((key, index) => (
            <div className="form-grid" key={key}>
              <label>
                Contact {index + 1} kind
                <select
                  name={`contactKind-${key}`}
                  required
                  defaultValue="email"
                >
                  {contactKinds.map((kind) => (
                    <option key={kind} value={kind}>
                      {kind}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Contact {index + 1} value
                <input
                  name={`contactValue-${key}`}
                  required
                  maxLength={320}
                  autoComplete="off"
                />
              </label>
              <label>
                Contact {index + 1} label (optional)
                <input name={`contactLabel-${key}`} maxLength={80} />
              </label>
              <div>
                <label className="checkbox-label">
                  <input name={`contactPrimary-${key}`} type="checkbox" />
                  Contact {index + 1} is primary
                </label>
                <label className="checkbox-label">
                  <input name={`contactWhatsapp-${key}`} type="checkbox" />
                  Contact {index + 1} supports WhatsApp
                </label>
              </div>
              <div className="form-actions">
                <button
                  className="button button-secondary button-small"
                  type="button"
                  onClick={() => removeContact(key)}
                >
                  Remove contact {index + 1}
                </button>
              </div>
            </div>
          ))}
          <div className="button-row">
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={contactKeys.length >= maximumContacts}
              onClick={addContact}
            >
              Add contact method
            </button>
          </div>
        </fieldset>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={createError}
          message={createMessage}
          permissionNotice="Your current membership cannot manage people."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={mutationDisabled || creating}
          >
            {creating ? "Creating…" : "Create person"}
          </button>
        </div>
      </form>
      <form className="form-card" onSubmit={(event) => void addProfile(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">People directory</p>
            <h2>Add a profile</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Person
            <select name="personId" required defaultValue="">
              <ResourceOptions
                includeIdentifier
                placeholder="Select a person"
                resources={people.items}
              />
            </select>
          </label>
          <label>
            Profile kind
            <select name="kind" required defaultValue="">
              <option value="" disabled>
                Select a profile kind
              </option>
              {profileKinds.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label>
            Title (optional)
            <input name="title" maxLength={80} />
          </label>
          <label className="form-span">
            Reference number (optional)
            <input
              name="referenceNumber"
              maxLength={64}
              autoComplete="off"
              spellCheck={false}
            />
            <small>Kept private; it is not shown in directory listings.</small>
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={profileError}
          message={profileMessage}
          permissionNotice="Your current membership cannot manage people."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              mutationDisabled || addingProfile || people.items.length === 0
            }
          >
            {addingProfile ? "Adding…" : "Add profile"}
          </button>
        </div>
      </form>
    </div>
  );
}
