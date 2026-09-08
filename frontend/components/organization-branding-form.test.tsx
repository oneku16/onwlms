import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrganizationBrandingForm } from "@/components/organization-branding-form";
import type { OrganizationConfigurationView } from "@/lib/api/organization";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const organization: OrganizationConfigurationView = {
  id: "org-1",
  slug: "north-valley",
  organizationType: "university",
  status: "active",
  branding: {
    displayName: "North Valley University",
    primaryColor: "#173F5F",
    secondaryColor: "#F0A43C",
    logo: null,
  },
  configuration: {
    locale: "en",
    timezone: "Asia/Bishkek",
    educationMode: "hybrid",
    customDomain: null,
    ownidTenantReference: "tenant-ref",
    ownidClientReference: null,
  },
};

function savedResponse(displayName: string) {
  return new Response(
    JSON.stringify({
      id: "org-1",
      slug: "north-valley",
      organization_type: "university",
      status: "active",
      branding: {
        display_name: displayName,
        primary_color: "#173f5f",
        secondary_color: "#f0a43c",
        logo: null,
      },
      configuration: {
        locale: "en",
        timezone: "Asia/Bishkek",
        education_mode: "flexible",
        custom_domain: {
          domain: "sis.nvu.example",
          verification_status: "pending",
        },
        ownid_tenant_reference: "tenant-ref",
        ownid_client_reference: null,
      },
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

describe("OrganizationBrandingForm", () => {
  it("replaces the full non-secret configuration from pre-filled values", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(savedResponse("North Valley University"));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <OrganizationBrandingForm
        canConfigure
        initialOrganization={organization}
        organizationId="org-1"
      />,
    );

    expect(screen.getByLabelText("Display name")).toHaveValue(
      "North Valley University",
    );
    expect(screen.getByLabelText("Timezone")).toHaveValue("Asia/Bishkek");
    fireEvent.change(screen.getByLabelText("Education mode"), {
      target: { value: "flexible" },
    });
    fireEvent.change(screen.getByLabelText(/^Custom domain/), {
      target: { value: "sis.nvu.example" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save configuration" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/organization");
    expect(options.method).toBe("PUT");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      branding: {
        display_name: "North Valley University",
        primary_color: "#173f5f",
        secondary_color: "#f0a43c",
        logo: null,
      },
      configuration: {
        locale: "en",
        timezone: "Asia/Bishkek",
        education_mode: "flexible",
        custom_domain: {
          domain: "sis.nvu.example",
          verification_status: "pending",
        },
        ownid_tenant_reference: "tenant-ref",
        ownid_client_reference: null,
      },
    });
    expect(
      await screen.findByText("Organization configuration saved."),
    ).toBeVisible();
    expect(screen.getByText("sis.nvu.example · pending")).toBeVisible();
  });

  it("requires explicit confirmation before clearing stored logo metadata", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <OrganizationBrandingForm
        canConfigure
        initialOrganization={{
          ...organization,
          branding: {
            ...organization.branding,
            logo: {
              fileName: "logo.png",
              contentType: "image/png",
              sizeBytes: 10,
            },
          },
        }}
        organizationId="org-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save configuration" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Confirm that the stored logo metadata will be cleared before saving.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
