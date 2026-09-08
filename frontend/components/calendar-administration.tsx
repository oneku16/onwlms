"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { EmptyState } from "@/components/states";
import { parseCalendarEventSummary } from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { appendResource, type ResourceCollection } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { isoFromDateTimeInput, textValue } from "@/lib/forms";

export function CalendarAdministration({
  canManage,
  initialEvents,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly initialEvents: ResourceCollection;
  readonly organizationId: string;
}) {
  const [events, setEvents] = useState(initialEvents);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createEvent(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const startsAt = isoFromDateTimeInput(form.get("startsAt"));
    const endsAt = isoFromDateTimeInput(form.get("endsAt"));
    if (!startsAt || !endsAt) {
      setError("Enter valid start and end times.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/calendar-events",
        parseCalendarEventSummary,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            title: textValue(form.get("title")),
            starts_at: startsAt,
            ends_at: endsAt,
            instruction_allowed: form.get("instructionAllowed") === "on",
          },
        },
      );
      setEvents((current) => appendResource(current, created));
      setMessage(`Calendar event “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The calendar event could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {events.items.length > 0 ? (
        <ResourceList collection={events} />
      ) : (
        <EmptyState message="No academic calendar events fall within the 180-day window around today." />
      )}
      <form className="form-card" onSubmit={(event) => void createEvent(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic calendar</p>
            <h2>Create a calendar event</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Event title
            <input name="title" required maxLength={255} />
          </label>
          <label>
            Starts at
            <input name="startsAt" type="datetime-local" required />
          </label>
          <label>
            Ends at
            <input name="endsAt" type="datetime-local" required />
          </label>
          <label className="checkbox-label form-span">
            <input name="instructionAllowed" type="checkbox" />
            Instruction is allowed during this event
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage the academic calendar."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!canManage || !csrfAvailable || submitting}
          >
            {submitting ? "Creating…" : "Create calendar event"}
          </button>
        </div>
      </form>
    </div>
  );
}
