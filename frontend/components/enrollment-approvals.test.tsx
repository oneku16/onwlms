import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EnrollmentApprovals } from "@/components/enrollment-approvals";
import type { CourseSelectionRequest } from "@/lib/api/course-selection";

const pendingRequest: CourseSelectionRequest = {
  id: "0198e706-a6d9-7b24-9156-7f92716f5f47",
  studentAcademicEnrollmentId: "0198e706-a6d9-7b24-9156-7f92716f5f43",
  termId: "0198e706-a6d9-7b24-9156-7f92716f5f44",
  offeringIds: ["0198e706-a6d9-7b24-9156-7f92716f5f45"],
  requestedCredits: "6.00",
  status: "pending",
  overrideReason: null,
  overriddenRules: [],
  rejectionReason: null,
};

function response(status: "approved" | "rejected", reason: string | null) {
  return new Response(
    JSON.stringify({
      id: pendingRequest.id,
      student_academic_enrollment_id:
        pendingRequest.studentAcademicEnrollmentId,
      term_id: pendingRequest.termId,
      offering_ids: pendingRequest.offeringIds,
      requested_credits: pendingRequest.requestedCredits,
      status,
      override_reason: null,
      overridden_rules: [],
      rejection_reason: reason,
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("EnrollmentApprovals", () => {
  it("approves a pending request with the exact PATCH body and CSRF protection", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(response("approved", null));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <EnrollmentApprovals
        canDecide
        initialRequests={[pendingRequest]}
        organizationId="org-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Approve 0198e706" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      `/api/v1/academics/course-selection-requests/${pendingRequest.id}/decision`,
    );
    expect(options.method).toBe("PATCH");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({ approved: true });
    expect(
      await screen.findByText("Course selection 0198e706 was approved."),
    ).toBeVisible();
    expect(
      screen.getByText("No course-selection requests are awaiting a decision."),
    ).toBeVisible();
  });

  it("rejects only with the entered required reason", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const rejectionReason = "The prerequisite record is incomplete.";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(response("rejected", rejectionReason));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <EnrollmentApprovals
        canDecide
        initialRequests={[pendingRequest]}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Rejection reason for 0198e706"), {
      target: { value: rejectionReason },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reject 0198e706" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      approved: false,
      reason: rejectionReason,
    });
    expect(
      await screen.findByText("Course selection 0198e706 was rejected."),
    ).toBeVisible();
  });
});
