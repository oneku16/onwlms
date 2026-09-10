"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  appendResource,
  parseCreatedResource,
  type ResourceCollection,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { positiveIntegerValue, textValue } from "@/lib/forms";

export function RoomAdministration({
  campuses,
  canManage,
  initialRooms,
  organizationId,
}: {
  readonly campuses: readonly ResourceSummary[];
  readonly canManage: boolean;
  readonly initialRooms: ResourceCollection;
  readonly organizationId: string;
}) {
  const [rooms, setRooms] = useState(initialRooms);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createRoom(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const capacity = positiveIntegerValue(form.get("capacity"));
    if (capacity === null) {
      setError("Enter the room capacity as a positive whole number.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/rooms",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            campus_id: textValue(form.get("campusId")),
            code: textValue(form.get("code")),
            room_type: textValue(form.get("roomType")),
            capacity,
          },
        },
      );
      setRooms((current) => appendResource(current, created));
      setMessage(`Room “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The room could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {rooms.items.length > 0 ? (
        <ResourceList collection={rooms} />
      ) : (
        <EmptyState message="No rooms are available." />
      )}
      <form className="form-card" onSubmit={(event) => void createRoom(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Facilities</p>
            <h2>Create a room</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Campus
            <select name="campusId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a campus"
                resources={campuses}
              />
            </select>
          </label>
          <label>
            Room code
            <input name="code" required maxLength={64} spellCheck={false} />
          </label>
          <label>
            Room type
            <input name="roomType" required maxLength={64} />
            <small>For example lecture, laboratory, or seminar.</small>
          </label>
          <label>
            Capacity
            <input name="capacity" type="number" min="1" step="1" required />
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage rooms."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              submitting ||
              campuses.length === 0
            }
          >
            {submitting ? "Creating…" : "Create room"}
          </button>
        </div>
      </form>
    </div>
  );
}
