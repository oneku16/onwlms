import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PeopleAdministration } from "@/components/people-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("PeopleAdministration", () => {
  it("creates a person with private identifiers and masked contacts", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "person-1",
          organization_id: "org-1",
          display_name: "Aida Sadykova",
          given_name: "Aida",
          family_name: "Sadykova",
          preferred_name: null,
          contacts: [
            {
              id: "contact-1",
              kind: "email",
              masked_value: "a***@example.test",
              label: "Work",
              is_primary: true,
              whatsapp_capable: false,
            },
          ],
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <PeopleAdministration
        canManage
        initialPeople={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Given name"), {
      target: { value: "Aida" },
    });
    fireEvent.change(screen.getByLabelText("Family name"), {
      target: { value: "Sadykova" },
    });
    fireEvent.change(screen.getByLabelText("Date of birth (optional)"), {
      target: { value: "2004-05-06" },
    });
    fireEvent.change(screen.getByLabelText("National identifier (optional)"), {
      target: { value: "PIN-123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add contact method" }));
    fireEvent.change(screen.getByLabelText("Contact 1 value"), {
      target: { value: "aida@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Contact 1 label (optional)"), {
      target: { value: "Work" },
    });
    fireEvent.click(screen.getByLabelText("Contact 1 is primary"));
    fireEvent.click(screen.getByRole("button", { name: "Create person" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/people");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(headers.get("idempotency-key")).toMatch(/[0-9a-f-]{36}/);
    expect(JSON.parse(String(options.body))).toEqual({
      given_name: "Aida",
      family_name: "Sadykova",
      preferred_name: null,
      date_of_birth: "2004-05-06",
      national_identifier: "PIN-123456",
      contacts: [
        {
          kind: "email",
          value: "aida@example.test",
          label: "Work",
          is_primary: true,
          whatsapp_capable: false,
        },
      ],
    });
    expect(
      await screen.findByText("Person “Aida Sadykova” was created."),
    ).toBeVisible();
    expect(document.body.textContent).not.toContain("PIN-123456");
    expect(document.body.textContent).not.toContain("aida@example.test");
    expect(screen.getByLabelText("National identifier (optional)")).toHaveValue(
      "",
    );
  });

  it("adds a profile to an existing person without echoing the reference number", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "profile-1",
          organization_id: "org-1",
          person_id: "person-1",
          kind: "teacher",
          title: "Dr.",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <PeopleAdministration
        canManage
        initialPeople={{
          items: [{ id: "person-1", title: "Aida Sadykova" }],
          total: 1,
        }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Person"), {
      target: { value: "person-1" },
    });
    fireEvent.change(screen.getByLabelText("Profile kind"), {
      target: { value: "teacher" },
    });
    fireEvent.change(screen.getByLabelText("Title (optional)"), {
      target: { value: "Dr." },
    });
    fireEvent.change(screen.getByLabelText(/^Reference number/), {
      target: { value: "T-0099" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add profile" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/people/person-1/profiles");
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual({
      kind: "teacher",
      reference_number: "T-0099",
      title: "Dr.",
    });
    expect(
      await screen.findByText("A teacher profile was added for Aida Sadykova."),
    ).toBeVisible();
    expect(document.body.textContent).not.toContain("T-0099");
  });
});
