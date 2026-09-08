import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SelectionPolicyAdministration } from "@/components/selection-policy-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const policy = {
  program_id: "program-1",
  term_id: "term-1",
  approval_required: true,
  deadline: "2026-08-30T18:00:00Z",
  education_mode: "flexible_selection",
  maximum_credits: "30.00",
};

function renderEditor() {
  return render(
    <SelectionPolicyAdministration
      canManage
      organizationId="org-1"
      programs={[{ id: "program-1", title: "Computer Science" }]}
      terms={[{ id: "term-1", title: "Autumn 2026" }]}
    />,
  );
}

function choosePair() {
  fireEvent.change(screen.getByLabelText("Program"), {
    target: { value: "program-1" },
  });
  fireEvent.change(screen.getByLabelText("Term"), {
    target: { value: "term-1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Load policy" }));
}

describe("SelectionPolicyAdministration", () => {
  it("configures a policy that does not exist yet", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockImplementation(
        async (_input: RequestInfo | URL, options?: RequestInit) =>
          options?.method === "PUT"
            ? new Response(JSON.stringify(policy), {
                status: 200,
                headers: { "content-type": "application/json" },
              })
            : new Response(
                JSON.stringify({
                  error: {
                    code: "not_found",
                    message: "Policy was not found.",
                  },
                }),
                {
                  status: 404,
                  headers: { "content-type": "application/json" },
                },
              ),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();
    choosePair();

    expect(
      await screen.findByText(
        "No course-selection policy exists for this program and term. Saving creates it.",
      ),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText(/^Selection deadline/), {
      target: { value: "2026-08-30T18:00" },
    });
    fireEvent.change(screen.getByLabelText("Maximum credits"), {
      target: { value: "30.00" },
    });
    fireEvent.change(screen.getByLabelText("Education mode"), {
      target: { value: "flexible_selection" },
    });
    fireEvent.click(
      screen.getByLabelText("Approval is required before enrollment"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save policy" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe(
      "/api/v1/academics/course-selection-policies/program-1/term-1",
    );
    expect(options.method).toBe("PUT");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      approval_required: true,
      deadline: new Date("2026-08-30T18:00").toISOString(),
      education_mode: "flexible_selection",
      maximum_credits: "30.00",
    });
    expect(
      await screen.findByText("Course-selection policy saved."),
    ).toBeVisible();
  });

  it("pre-fills an existing policy", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(policy), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    renderEditor();
    choosePair();

    expect(await screen.findByLabelText("Maximum credits")).toHaveValue(
      "30.00",
    );
    expect(screen.getByLabelText("Education mode")).toHaveValue(
      "flexible_selection",
    );
    expect(
      screen.getByLabelText("Approval is required before enrollment"),
    ).toBeChecked();
    expect(screen.getByText("configured")).toBeVisible();
  });
});
