import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProvisioningAdministration } from "@/components/provisioning-administration";
import type { ProvisioningJobView } from "@/lib/api/provisioning";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const retryJob: ProvisioningJobView = {
  id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
  subjectType: "person",
  subjectId: "0198e706-a6d9-7b24-9156-7f92716f5f44",
  target: "moodle",
  status: "retry",
  attempts: 1,
  createdAt: "2026-08-07T09:00:00Z",
  updatedAt: "2026-08-07T09:05:00Z",
  externalReference: null,
  lastErrorCode: "timeout",
};

const failedJob: ProvisioningJobView = {
  ...retryJob,
  id: "0198e706-a6d9-7b24-9156-7f92716f5f45",
  target: "ownid",
  status: "failed",
};

describe("ProvisioningAdministration", () => {
  it("retries only retryable jobs through the audited retry action", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: retryJob.id,
          subject_type: "person",
          subject_id: retryJob.subjectId,
          target: "moodle",
          status: "succeeded",
          attempts: 2,
          created_at: retryJob.createdAt,
          updated_at: "2026-08-07T09:10:00Z",
          external_reference: "moodle-user-7",
          last_error_code: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ProvisioningAdministration
        canRetry
        initialJobs={[retryJob, failedJob]}
        organizationId="org-1"
      />,
    );

    expect(
      screen.queryByRole("button", { name: /^Retry ownid/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Retry moodle 0198e706" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(`/api/v1/operations/provisioning/${retryJob.id}/retry`);
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(
      await screen.findByText(
        "moodle provisioning 0198e706 was retried and is now succeeded.",
      ),
    ).toBeVisible();
    expect(screen.getByText("succeeded")).toBeVisible();
    expect(screen.getByText("moodle-user-7")).toBeVisible();
  });

  it("disables retries without the retry permission", () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    render(
      <ProvisioningAdministration
        canRetry={false}
        initialJobs={[retryJob]}
        organizationId="org-1"
      />,
    );
    expect(
      screen.getByRole("button", { name: "Retry moodle 0198e706" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Your current membership cannot retry provisioning jobs.",
      ),
    ).toBeVisible();
  });
});
