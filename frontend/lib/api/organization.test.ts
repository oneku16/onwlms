import { describe, expect, it } from "vitest";

import {
  parseCampus,
  parseOrganizationConfiguration,
} from "@/lib/api/organization";

const organization = {
  id: "0198c1c0-1111-7000-8000-000000000001",
  slug: "north-valley",
  organization_type: "university",
  status: "active",
  branding: {
    display_name: "North Valley University",
    primary_color: "#173F5F",
    secondary_color: "#F0A43C",
    logo: null,
  },
  configuration: {
    locale: "en",
    timezone: "Asia/Bishkek",
    education_mode: "hybrid",
    custom_domain: {
      domain: "sis.nvu.example",
      verification_status: "pending",
    },
    ownid_tenant_reference: "tenant-ref",
    ownid_client_reference: null,
  },
};

describe("organization configuration contract", () => {
  it("parses the full replaceable configuration including nullable metadata", () => {
    expect(parseOrganizationConfiguration(organization)).toEqual({
      id: organization.id,
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
        customDomain: {
          domain: "sis.nvu.example",
          verificationStatus: "pending",
        },
        ownidTenantReference: "tenant-ref",
        ownidClientReference: null,
      },
    });
  });

  it("keeps logo metadata without inventing an object key", () => {
    const parsed = parseOrganizationConfiguration({
      ...organization,
      branding: {
        ...organization.branding,
        logo: {
          file_name: "logo.png",
          content_type: "image/png",
          size_bytes: 10,
        },
      },
    });
    expect(parsed.branding.logo).toEqual({
      fileName: "logo.png",
      contentType: "image/png",
      sizeBytes: 10,
    });
    expect(() =>
      parseOrganizationConfiguration({
        ...organization,
        configuration: { ...organization.configuration, education_mode: "x" },
      }),
    ).toThrow("The organization configuration response is not supported.");
  });

  it("parses created campuses", () => {
    expect(
      parseCampus({
        id: "campus-1",
        organization_id: organization.id,
        code: "NV",
        name: "North Valley",
        active: true,
      }),
    ).toEqual({
      id: "campus-1",
      code: "NV",
      name: "North Valley",
      active: true,
    });
  });
});
