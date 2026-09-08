"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { offeringLabel } from "@/components/course-offering-administration";
import { FormFeedback } from "@/components/form-feedback";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import {
  parseTeacherAssignment,
  type CourseOfferingView,
  type TeacherAssignmentView,
} from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { resourceTitle, type ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { textValue } from "@/lib/forms";

export function TeacherAssignmentAdministration({
  canManage,
  courses,
  initialAssignments,
  offerings,
  organizationId,
  teachers,
  terms,
}: {
  readonly canManage: boolean;
  readonly courses: readonly ResourceSummary[];
  readonly initialAssignments: readonly TeacherAssignmentView[];
  readonly offerings: readonly CourseOfferingView[];
  readonly organizationId: string;
  readonly teachers: readonly ResourceSummary[];
  readonly terms: readonly ResourceSummary[];
}) {
  const [assignments, setAssignments] = useState(initialAssignments);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();
  const offeringOptions: readonly ResourceSummary[] = offerings.map(
    (offering) => ({
      id: offering.id,
      title: offeringLabel(offering, courses, terms),
    }),
  );

  function describeOffering(offeringId: string): string {
    return resourceTitle(offeringOptions, offeringId, "Offering");
  }

  async function assignTeacher(
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
        "/api/v1/academics/teacher-assignments",
        parseTeacherAssignment,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            course_offering_id: textValue(form.get("courseOfferingId")),
            teacher_id: textValue(form.get("teacherId")),
            role: textValue(form.get("role")),
          },
        },
      );
      setAssignments((current) => [...current, created]);
      setMessage(
        `${resourceTitle(teachers, created.teacherId, "Teacher")} was assigned to ${describeOffering(created.courseOfferingId)} as ${created.role}.`,
      );
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The teacher assignment could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {assignments.length === 0 ? (
        <EmptyState message="No teacher assignments are available." />
      ) : (
        <section aria-labelledby="teacher-assignments-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current records</p>
              <h2 id="teacher-assignments-heading">
                {assignments.length.toLocaleString()} teacher assignment
                {assignments.length === 1 ? "" : "s"}
              </h2>
            </div>
          </div>
          <div className="resource-grid">
            {assignments.map((assignment) => (
              <article className="resource-card" key={assignment.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>
                      {resourceTitle(teachers, assignment.teacherId, "Teacher")}
                    </h2>
                    <p>{describeOffering(assignment.courseOfferingId)}</p>
                  </div>
                  <span className="status-pill">{assignment.role}</span>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
      <form
        className="form-card"
        onSubmit={(event) => void assignTeacher(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Teaching responsibilities</p>
            <h2>Assign a teacher</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Course offering
            <select name="courseOfferingId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a course offering"
                resources={offeringOptions}
              />
            </select>
          </label>
          <label>
            Teacher profile
            <select name="teacherId" required defaultValue="">
              <ResourceOptions
                includeIdentifier
                placeholder="Select a tenant teacher"
                resources={teachers}
              />
            </select>
          </label>
          <label>
            Role
            <input
              name="role"
              required
              maxLength={64}
              defaultValue="lecturer"
            />
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage teacher assignments."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              submitting ||
              offerings.length === 0 ||
              teachers.length === 0
            }
          >
            {submitting ? "Assigning…" : "Assign teacher"}
          </button>
        </div>
      </form>
    </div>
  );
}
