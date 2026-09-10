import { describe, expect, it } from "vitest";

import {
  isRetryableProvisioningJob,
  parseProvisioningJobs,
} from "@/lib/api/provisioning";

describe("provisioning job contract", () => {
  it("parses privacy-safe jobs and marks only pending or retry jobs retryable", () => {
    const jobs = parseProvisioningJobs([
      {
        id: "job-1",
        subject_type: "person",
        subject_id: "person-1",
        target: "moodle",
        status: "retry",
        attempts: 1,
        created_at: "2026-08-07T09:00:00Z",
        updated_at: "2026-08-07T09:05:00Z",
        external_reference: null,
        last_error_code: "timeout",
      },
      {
        id: "job-2",
        subject_type: "person",
        subject_id: "person-1",
        target: "ownid",
        status: "failed",
        attempts: 3,
        created_at: "2026-08-07T09:00:00Z",
        updated_at: "2026-08-07T09:05:00Z",
        external_reference: "ref-1",
        last_error_code: "adapter_not_configured",
      },
    ]);
    expect(jobs[0]).toEqual({
      id: "job-1",
      subjectType: "person",
      subjectId: "person-1",
      target: "moodle",
      status: "retry",
      attempts: 1,
      createdAt: "2026-08-07T09:00:00Z",
      updatedAt: "2026-08-07T09:05:00Z",
      externalReference: null,
      lastErrorCode: "timeout",
    });
    expect(jobs.map(isRetryableProvisioningJob)).toEqual([true, false]);
    expect(() => parseProvisioningJobs([{ id: "job-3" }])).toThrow(
      "The provisioning job response is not supported.",
    );
  });
});
