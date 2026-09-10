import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdmissionsWorkflow } from "@/components/admissions-workflow";
import type { ApplicationView } from "@/lib/api/admissions";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const applicationId = "0198e706-a6d9-7b24-9156-7f92716f5f43";

const draft: ApplicationView = {
  id: applicationId,
  applicantProfileId: "0198e706-a6d9-7b24-9156-7f92716f5f44",
  programId: "program-1",
  intakeId: "term-1",
  seatCategory: "general",
  source: "administrator_entered",
  status: "draft",
  depositStatus: "not_required",
  depositRequired: false,
  createdAt: "2026-08-07T09:00:00Z",
  statusChangedAt: "2026-08-07T09:00:00Z",
};

function applicationPayload(status: string, id = applicationId) {
  return {
    id,
    applicant_profile_id: draft.applicantProfileId,
    program_id: "program-1",
    intake_id: "term-1",
    seat_category: "general",
    source: "administrator_entered",
    status,
    deposit_status: "not_required",
    deposit_required: false,
    deposit_amount: null,
    deposit_currency: null,
    deposit_due_at: null,
    created_at: "2026-08-07T09:00:00Z",
    status_changed_at: "2026-08-08T09:00:00Z",
  };
}

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderWorkflow(
  applications: readonly ApplicationView[],
  overrides: Partial<Parameters<typeof AdmissionsWorkflow>[0]> = {},
) {
  return render(
    <AdmissionsWorkflow
      canCreate
      canDecide
      canEnroll
      canManageDocuments
      canReview
      canSubmit
      initialApplications={applications}
      organizationId="org-1"
      programs={[{ id: "program-1", title: "Computer Science" }]}
      terms={[{ id: "term-1", title: "Autumn 2026" }]}
      {...overrides}
    />,
  );
}

describe("AdmissionsWorkflow", () => {
  it("creates an administrator-entered application without echoing contacts", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(json(applicationPayload("draft"), 201));
    vi.stubGlobal("fetch", fetchMock);
    renderWorkflow([]);

    expect(
      screen.getByText("No admissions applications match the current filter."),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Given name"), {
      target: { value: "Aida" },
    });
    fireEvent.change(screen.getByLabelText("Family name"), {
      target: { value: "Sadykova" },
    });
    fireEvent.change(screen.getByLabelText("Email (optional)"), {
      target: { value: "aida@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Program"), {
      target: { value: "program-1" },
    });
    fireEvent.change(screen.getByLabelText("Intake term"), {
      target: { value: "term-1" },
    });
    fireEvent.change(screen.getByLabelText("Seat category"), {
      target: { value: "general" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create application" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/admissions/applications");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(headers.get("idempotency-key")).toMatch(/[0-9a-f-]{36}/);
    expect(JSON.parse(String(options.body))).toEqual({
      given_name: "Aida",
      family_name: "Sadykova",
      email: "aida@example.test",
      phone: null,
      program_id: "program-1",
      intake_id: "term-1",
      seat_category: "general",
      source: "administrator_entered",
    });
    expect(
      await screen.findByText(
        "Application 0198e706 was created with status draft. Applicant contact details are not shown again.",
      ),
    ).toBeVisible();
    expect(screen.getByText("1 application")).toBeVisible();
    expect(document.body.textContent).not.toContain("aida@example.test");
  });

  it("filters the list by application status", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(json([applicationPayload("submitted")]));
    vi.stubGlobal("fetch", fetchMock);
    renderWorkflow([draft]);

    fireEvent.change(screen.getByLabelText("Application status"), {
      target: { value: "submitted" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filter" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/admissions/applications?limit=100&application_status=submitted",
    );
    await waitFor(() =>
      expect(
        screen
          .getAllByText("submitted")
          .some((element) => element.classList.contains("status-pill")),
      ).toBe(true),
    );
    expect(
      screen
        .getAllByText("draft")
        .some((element) => element.classList.contains("status-pill")),
    ).toBe(false);
  });

  it("loads history for the selected application and records a review", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockImplementation(
        async (input: RequestInfo | URL, options?: RequestInit) => {
          const path = String(input);
          if (options?.method === "POST") {
            return json(
              {
                id: "review-2",
                application_id: applicationId,
                stage: "exam",
                outcome: "passed",
                explanation: "Score 88.",
              },
              201,
            );
          }
          if (path.endsWith("/reviews?limit=100")) {
            return json([
              {
                id: "review-1",
                application_id: applicationId,
                stage: "document_review",
                outcome: "passed",
                explanation: null,
              },
            ]);
          }
          if (path.endsWith("/documents?limit=100")) {
            return json([
              {
                id: "document-1",
                application_id: applicationId,
                document_type: "passport",
                file_reference: "s3://bucket/passport.pdf",
                media_type: "application/pdf",
                size_bytes: 1024,
                checksum_sha256: "a".repeat(64),
                uploaded_at: "2026-08-07T09:00:00Z",
              },
            ]);
          }
          return json(applicationPayload("under_review"));
        },
      );
    vi.stubGlobal("fetch", fetchMock);
    renderWorkflow([{ ...draft, status: "submitted" }]);

    fireEvent.click(screen.getByRole("button", { name: "Select 0198e706" }));

    expect(await screen.findByText("document_review · passed")).toBeVisible();
    expect(screen.getByText("passport · application/pdf")).toBeVisible();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      `/api/v1/admissions/applications/${applicationId}/reviews?limit=100`,
      `/api/v1/admissions/applications/${applicationId}/documents?limit=100`,
    ]);

    fireEvent.change(screen.getByLabelText("Review stage"), {
      target: { value: "exam" },
    });
    fireEvent.change(screen.getByLabelText("Review outcome"), {
      target: { value: "passed" },
    });
    fireEvent.change(screen.getByLabelText("Review explanation (optional)"), {
      target: { value: "Score 88." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record review" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const [path, options] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(path).toBe(
      `/api/v1/admissions/applications/${applicationId}/reviews`,
    );
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      stage: "exam",
      outcome: "passed",
      explanation: "Score 88.",
    });
    expect(fetchMock.mock.calls[3]?.[0]).toBe(
      `/api/v1/admissions/applications/${applicationId}`,
    );
    expect(
      await screen.findByText("Recorded the exam review as passed."),
    ).toBeVisible();
    expect(screen.getByText("exam · passed")).toBeVisible();
    expect(screen.getAllByText("under_review").length).toBeGreaterThan(0);
  });

  it("submits drafts and converts accepted applications", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockImplementation(
        async (input: RequestInfo | URL, options?: RequestInit) => {
          const path = String(input);
          if (path.endsWith("/submit")) {
            return json(applicationPayload("submitted"));
          }
          if (path.endsWith("/enrollment")) {
            return json(
              {
                student_id: "0198e706-a6d9-7b24-9156-7f92716f5f50",
                academic_enrollment_id: "0198e706-a6d9-7b24-9156-7f92716f5f51",
              },
              201,
            );
          }
          if (options?.method === "GET" && path.endsWith("?limit=100")) {
            return json([]);
          }
          return json(applicationPayload("enrolled", "accepted-1"));
        },
      );
    vi.stubGlobal("fetch", fetchMock);
    renderWorkflow([draft, { ...draft, id: "accepted-1", status: "accepted" }]);

    fireEvent.click(screen.getByRole("button", { name: "Select 0198e706" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Submit application" }),
    );
    expect(
      await screen.findByText(
        "Application 0198e706 was submitted and is now submitted.",
      ),
    ).toBeVisible();
    const submitCall = fetchMock.mock.calls.find(
      ([, options]) =>
        String((options as RequestInit | undefined)?.method) === "POST",
    );
    expect(submitCall?.[0]).toBe(
      `/api/v1/admissions/applications/${applicationId}/submit`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Select accepted" }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Enroll accepted application",
      }),
    );
    expect(
      await screen.findByText(
        "Application accepted was converted: student 0198e706, academic enrollment 0198e706.",
      ),
    ).toBeVisible();
    const enrollmentCall = fetchMock.mock.calls.find(([path]) =>
      String(path).endsWith("/enrollment"),
    );
    expect(enrollmentCall?.[0]).toBe(
      "/api/v1/admissions/applications/accepted-1/enrollment",
    );
    expect(
      new Headers((enrollmentCall?.[1] as RequestInit).headers).get(
        "idempotency-key",
      ),
    ).toMatch(/[0-9a-f-]{36}/);
    expect(screen.getAllByText("enrolled").length).toBeGreaterThan(0);
  });
});
