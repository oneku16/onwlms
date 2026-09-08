import { describe, expect, it } from "vitest";

import {
  parseAdmissionQuota,
  parseAdmissionsPolicy,
  parseApplicationDocuments,
  parseApplications,
  parseDecision,
  parseEnrollmentConversion,
  parseReviews,
} from "@/lib/api/admissions";

const application = {
  id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
  applicant_profile_id: "0198e706-a6d9-7b24-9156-7f92716f5f44",
  program_id: "0198e706-a6d9-7b24-9156-7f92716f5f45",
  intake_id: "0198e706-a6d9-7b24-9156-7f92716f5f46",
  seat_category: "general",
  source: "administrator_entered",
  status: "submitted",
  deposit_status: "not_required",
  deposit_required: false,
  deposit_amount: null,
  deposit_currency: null,
  deposit_due_at: null,
  created_at: "2026-08-07T09:00:00Z",
  status_changed_at: "2026-08-08T09:00:00Z",
};

describe("admissions contracts", () => {
  it("parses applications without applicant contact information", () => {
    expect(parseApplications([application])).toEqual([
      {
        id: application.id,
        applicantProfileId: application.applicant_profile_id,
        programId: application.program_id,
        intakeId: application.intake_id,
        seatCategory: "general",
        source: "administrator_entered",
        status: "submitted",
        depositStatus: "not_required",
        depositRequired: false,
        createdAt: "2026-08-07T09:00:00Z",
        statusChangedAt: "2026-08-08T09:00:00Z",
      },
    ]);
    expect(() =>
      parseApplications([{ ...application, status: "unknown" }]),
    ).toThrow("The admissions application response is not supported.");
  });

  it("parses reviews, document metadata, decisions, and conversions", () => {
    expect(
      parseReviews([
        {
          id: "review-1",
          application_id: application.id,
          stage: "exam",
          outcome: "passed",
          explanation: null,
        },
      ]),
    ).toEqual([
      {
        id: "review-1",
        applicationId: application.id,
        stage: "exam",
        outcome: "passed",
        explanation: null,
      },
    ]);
    expect(
      parseApplicationDocuments([
        {
          id: "document-1",
          application_id: application.id,
          document_type: "passport",
          file_reference: "s3://bucket/passport.pdf",
          media_type: "application/pdf",
          size_bytes: 1024,
          checksum_sha256: "a".repeat(64),
          uploaded_at: "2026-08-07T09:00:00Z",
        },
      ])[0],
    ).toEqual({
      id: "document-1",
      applicationId: application.id,
      documentType: "passport",
      fileReference: "s3://bucket/passport.pdf",
      mediaType: "application/pdf",
      sizeBytes: 1024,
      uploadedAt: "2026-08-07T09:00:00Z",
    });
    expect(
      parseDecision({
        id: "decision-1",
        application_id: application.id,
        outcome: "accepted",
        reason: "Met all requirements.",
        reservation_id: "reservation-1",
      }).reservationId,
    ).toBe("reservation-1");
    expect(
      parseEnrollmentConversion({
        student_id: "student-1",
        academic_enrollment_id: "enrollment-1",
      }),
    ).toEqual({ studentId: "student-1", academicEnrollmentId: "enrollment-1" });
  });

  it("parses policies and quotas with their defaults", () => {
    expect(
      parseAdmissionsPolicy({
        program_id: "program-1",
        intake_id: "intake-1",
        reservation_duration_seconds: 86400,
      }),
    ).toEqual({
      programId: "program-1",
      intakeId: "intake-1",
      requiredStages: [],
      depositRequired: false,
      depositAmount: null,
      depositCurrency: null,
      reservationDurationSeconds: 86400,
    });
    expect(() =>
      parseAdmissionsPolicy({
        program_id: "program-1",
        intake_id: "intake-1",
        required_stages: ["unknown"],
        reservation_duration_seconds: 86400,
      }),
    ).toThrow("The admissions policy response is not supported.");
    expect(
      parseAdmissionQuota({
        id: "quota-1",
        program_id: "program-1",
        intake_id: "intake-1",
        seat_category: "general",
        capacity: 40,
      }),
    ).toEqual({
      id: "quota-1",
      programId: "program-1",
      intakeId: "intake-1",
      seatCategory: "general",
      capacity: 40,
    });
  });
});
