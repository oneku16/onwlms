import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GuardianAdministration } from "@/components/guardian-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("GuardianAdministration", () => {
  it("links a guardian profile to a student profile", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "relationship-1",
          organization_id: "org-1",
          guardian_profile_id: "guardian-1",
          student_profile_id: "student-1",
          relationship_label: "mother",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <GuardianAdministration
        canManage
        initialGuardians={{
          items: [{ id: "guardian-1", title: "Guardian profile" }],
          total: 1,
        }}
        organizationId="org-1"
        students={[{ id: "student-1", title: "Student profile" }]}
      />,
    );

    expect(
      screen.getByRole("option", { name: "Guardian profile · guardian" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Guardian profile"), {
      target: { value: "guardian-1" },
    });
    fireEvent.change(screen.getByLabelText("Student profile"), {
      target: { value: "student-1" },
    });
    fireEvent.change(screen.getByLabelText(/^Relationship label/), {
      target: { value: "mother" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Link guardian" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/guardian-relationships");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      guardian_profile_id: "guardian-1",
      student_profile_id: "student-1",
      relationship_label: "mother",
    });
    expect(
      await screen.findByText(
        "Guardian profile → Student profile was linked as “mother”.",
      ),
    ).toBeVisible();
    expect(screen.getByText("mother")).toBeVisible();
  });

  it("disables linking without the guardian permission", () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    render(
      <GuardianAdministration
        canManage={false}
        initialGuardians={{ items: [], total: 0 }}
        organizationId="org-1"
        students={[]}
      />,
    );
    expect(screen.getByText("No guardians are available.")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Link guardian" }),
    ).toBeDisabled();
  });
});
