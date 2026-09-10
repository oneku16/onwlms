import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GradeEvidenceReview } from "@/components/grade-evidence-review";
import type {
  GradeEvidenceView,
  ReconciliationRunView,
} from "@/lib/api/integrations";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const pendingEvidence: GradeEvidenceView = {
  id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
  externalEventId: "moodle:grade:77",
  courseOfferingId: "0198e706-a6d9-7b24-9156-7f92716f5f44",
  studentPersonId: "0198e706-a6d9-7b24-9156-7f92716f5f45",
  gradeValue: "87.5",
  observedAt: "2026-09-08T12:00:00Z",
  sourceVersion: "moodle-webservice-v1",
  status: "pending",
  reasonCode: "review_required",
  receivedAt: "2026-09-08T12:00:05Z",
  acceptedFinalGradeId: null,
  resolvedAt: null,
};

const scales = [{ id: "scale-1", title: "Official percentage" }];
const terms = [{ id: "term-1", title: "Autumn 2026" }];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderReview(
  overrides: Partial<Parameters<typeof GradeEvidenceReview>[0]> = {},
) {
  return render(
    <GradeEvidenceReview
      canReconcile
      canReview
      gradingScales={scales}
      initialEvidence={[pendingEvidence]}
      initialRuns={[]}
      organizationId="org-1"
      terms={terms}
      {...overrides}
    />,
  );
}

describe("GradeEvidenceReview", () => {
  it("accepts evidence as an official grade with the selected scale", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ id: "grade-1", revision_number: 0 }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ...pendingEvidence,
            external_event_id: pendingEvidence.externalEventId,
            course_offering_id: pendingEvidence.courseOfferingId,
            student_person_id: pendingEvidence.studentPersonId,
            grade_value: pendingEvidence.gradeValue,
            observed_at: pendingEvidence.observedAt,
            source_version: pendingEvidence.sourceVersion,
            received_at: pendingEvidence.receivedAt,
            status: "accepted",
            reason_code: null,
            accepted_final_grade_id: "grade-1",
            resolved_at: "2026-09-08T13:00:00Z",
          },
        ]),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderReview();

    fireEvent.change(screen.getByLabelText(/^Grading scale for/), {
      target: { value: "scale-1" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Accept as official grade" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      `/api/v1/grading/external-evidence/${pendingEvidence.id}/accept`,
    );
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      grading_scale_id: "scale-1",
    });
    expect(
      await screen.findByText(
        "Evidence 0198e706 became official grade grade-1.",
      ),
    ).toBeVisible();
    expect(screen.getByText("accepted")).toBeVisible();
  });

  it("sends an explanation when one is supplied for a revision", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ id: "grade-1", revision_number: 1 }),
      )
      .mockResolvedValueOnce(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    renderReview();

    fireEvent.change(screen.getByLabelText(/^Grading scale for/), {
      target: { value: "scale-1" },
    });
    fireEvent.change(screen.getByLabelText(/^Explanation for/), {
      target: { value: "Moodle total supersedes the provisional mark." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Accept as official grade" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(options.body))).toEqual({
      grading_scale_id: "scale-1",
      explanation: "Moodle total supersedes the provisional mark.",
    });
    expect(
      await screen.findByText(
        "Evidence 0198e706 revised official grade grade-1 to revision 1.",
      ),
    ).toBeVisible();
  });

  it("requires a reason before rejecting evidence", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderReview();

    fireEvent.click(screen.getByRole("button", { name: "Reject evidence" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A rejection reason is required.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects evidence with an audited reason", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ evidence_id: pendingEvidence.id, status: "rejected" }),
      )
      .mockResolvedValueOnce(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    renderReview();

    fireEvent.change(screen.getByLabelText(/^Rejection reason for/), {
      target: { value: "Student withdrew before the total was final." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reject evidence" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      `/api/v1/grading/external-evidence/${pendingEvidence.id}/reject`,
    );
    expect(JSON.parse(String(options.body))).toEqual({
      reason: "Student withdrew before the total was final.",
    });
    expect(
      await screen.findByText("Evidence 0198e706 was rejected."),
    ).toBeVisible();
  });

  it("reports reconciliation counts without inventing unmapped results", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const run: ReconciliationRunView = {
      id: "run-0001",
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
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            id: run.id,
            term_id: run.termId,
            status: run.status,
            started_at: run.startedAt,
            finished_at: run.finishedAt,
            offering_count: run.offeringCount,
            unmapped_offering_count: run.unmappedOfferingCount,
            observed_count: run.observedCount,
            new_evidence_count: run.newEvidenceCount,
            duplicate_count: run.duplicateCount,
            unmapped_user_count: run.unmappedUserCount,
            error_code: null,
          },
          201,
        ),
      )
      .mockResolvedValueOnce(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    renderReview();

    fireEvent.change(screen.getByLabelText("Term"), {
      target: { value: "term-1" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Reconcile term grades" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/integrations/moodle/grade-reconciliations");
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("idempotency-key")).toBeTruthy();
    expect(JSON.parse(String(options.body))).toEqual({ term_id: "term-1" });
    expect(
      await screen.findByText(
        "Run run-0001 observed 9 totals and stored 3 new evidence records.",
      ),
    ).toBeVisible();
    expect(screen.getByText("Reconciliation runs")).toBeVisible();
  });

  it("disables decisions without the grading permission", () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    renderReview({ canReview: false, canReconcile: false });

    expect(
      screen.getByRole("button", { name: "Accept as official grade" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Reject evidence" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Reconcile term grades" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Your current membership cannot accept or reject grade evidence.",
      ),
    ).toBeVisible();
  });
});
