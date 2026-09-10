import { describe, expect, it } from "vitest";

import {
  parseGradeEvidenceList,
  parseMoodleStatus,
  parseReconciliationRun,
  parseReconciliationRuns,
} from "@/lib/api/integrations";

describe("Moodle status contract", () => {
  it("parses configured and disabled states without credential fields", () => {
    expect(
      parseMoodleStatus({
        configured: true,
        base_url: "https://moodle.example.test",
        status: "healthy",
        last_success_at: "2026-08-07T09:00:00Z",
        last_error_code: null,
        grade_events_configured: true,
      }),
    ).toEqual({
      configured: true,
      baseUrl: "https://moodle.example.test",
      status: "healthy",
      lastSuccessAt: "2026-08-07T09:00:00Z",
      lastErrorCode: null,
      gradeEventsConfigured: true,
    });
    expect(
      parseMoodleStatus({
        configured: false,
        base_url: null,
        status: "disabled",
        last_success_at: null,
        last_error_code: null,
      }),
    ).toMatchObject({ configured: false, gradeEventsConfigured: false });
    expect(() => parseMoodleStatus({ configured: "yes" })).toThrow(
      "The Moodle status response is not supported.",
    );
  });
});

const evidencePayload = {
  id: "evidence-1",
  external_event_id: "moodle:grade:77",
  course_offering_id: "offering-1",
  student_person_id: "person-1",
  grade_value: "87.5",
  observed_at: "2026-09-08T12:00:00Z",
  source_version: "moodle-webservice-v1",
  status: "pending",
  reason_code: "review_required",
  received_at: "2026-09-08T12:00:05Z",
  accepted_final_grade_id: null,
  resolved_at: null,
};

describe("Moodle grade-evidence contract", () => {
  it("parses stored evidence with provenance and resolution state", () => {
    const [evidence] = parseGradeEvidenceList([evidencePayload]);

    expect(evidence).toEqual({
      id: "evidence-1",
      externalEventId: "moodle:grade:77",
      courseOfferingId: "offering-1",
      studentPersonId: "person-1",
      gradeValue: "87.5",
      observedAt: "2026-09-08T12:00:00Z",
      sourceVersion: "moodle-webservice-v1",
      status: "pending",
      reasonCode: "review_required",
      receivedAt: "2026-09-08T12:00:05Z",
      acceptedFinalGradeId: null,
      resolvedAt: null,
    });
  });

  it("rejects evidence responses that are missing required provenance", () => {
    expect(() =>
      parseGradeEvidenceList([{ ...evidencePayload, observed_at: undefined }]),
    ).toThrow("The Moodle grade-evidence response is not supported.");
    expect(() => parseGradeEvidenceList({ items: [] })).toThrow(
      "The Moodle grade-evidence response is not supported.",
    );
  });
});

const runPayload = {
  id: "run-1",
  term_id: "term-1",
  status: "succeeded",
  started_at: "2026-09-08T12:00:00Z",
  finished_at: "2026-09-08T12:00:30Z",
  offering_count: 4,
  unmapped_offering_count: 1,
  observed_count: 9,
  new_evidence_count: 3,
  duplicate_count: 6,
  unmapped_user_count: 2,
  error_code: null,
};

describe("Moodle reconciliation contract", () => {
  it("parses run counts that explain unobserved work", () => {
    expect(parseReconciliationRun(runPayload)).toEqual({
      id: "run-1",
      termId: "term-1",
      status: "succeeded",
      startedAt: "2026-09-08T12:00:00Z",
      finishedAt: "2026-09-08T12:00:30Z",
      offeringCount: 4,
      unmappedOfferingCount: 1,
      observedCount: 9,
      newEvidenceCount: 3,
      duplicateCount: 6,
      unmappedUserCount: 2,
      errorCode: null,
    });
    expect(parseReconciliationRuns([runPayload])).toHaveLength(1);
  });

  it("rejects runs with missing or negative counts", () => {
    expect(() =>
      parseReconciliationRun({ ...runPayload, observed_count: -1 }),
    ).toThrow("The reconciliation run response is not supported.");
    expect(() =>
      parseReconciliationRun({ ...runPayload, offering_count: undefined }),
    ).toThrow("The reconciliation run response is not supported.");
  });
});
