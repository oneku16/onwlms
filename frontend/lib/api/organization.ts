import {
  asBoolean,
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export const organizationEducationModes = [
  "fixed",
  "flexible",
  "hybrid",
] as const;

export type OrganizationEducationMode =
  (typeof organizationEducationModes)[number];

export interface LogoMetadataView {
  readonly fileName: string;
  readonly contentType: string;
  readonly sizeBytes: number;
}

export interface CustomDomainView {
  readonly domain: string;
  readonly verificationStatus: string;
}

export interface OrganizationConfigurationView {
  readonly id: string;
  readonly slug: string;
  readonly organizationType: string;
  readonly status: string;
  readonly branding: {
    readonly displayName: string;
    readonly primaryColor: string;
    readonly secondaryColor: string;
    readonly logo: LogoMetadataView | null;
  };
  readonly configuration: {
    readonly locale: string;
    readonly timezone: string;
    readonly educationMode: OrganizationEducationMode;
    readonly customDomain: CustomDomainView | null;
    readonly ownidTenantReference: string | null;
    readonly ownidClientReference: string | null;
  };
}

const contract = "organization configuration";

function requireRecord(value: unknown): UnknownRecord {
  const record = asRecord(value);
  if (!record) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return record;
}

function requireString(record: UnknownRecord, key: string): string {
  const value = asString(record[key]);
  if (!value) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return value;
}

function nullableString(record: UnknownRecord, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  return requireString(record, key);
}

function isEducationMode(value: string): value is OrganizationEducationMode {
  return organizationEducationModes.some((mode) => mode === value);
}

function parseLogo(value: unknown): LogoMetadataView | null {
  if (value === null || value === undefined) {
    return null;
  }
  const record = requireRecord(value);
  const sizeBytes = asNumber(record.size_bytes);
  if (sizeBytes === undefined) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    fileName: requireString(record, "file_name"),
    contentType: requireString(record, "content_type"),
    sizeBytes,
  };
}

function parseCustomDomain(value: unknown): CustomDomainView | null {
  if (value === null || value === undefined) {
    return null;
  }
  const record = requireRecord(value);
  return {
    domain: requireString(record, "domain"),
    verificationStatus: requireString(record, "verification_status"),
  };
}

export function parseOrganizationConfiguration(
  value: unknown,
): OrganizationConfigurationView {
  const record = requireRecord(unwrapPayload(value));
  const branding = requireRecord(record.branding);
  const configuration = requireRecord(record.configuration);
  const educationMode = requireString(configuration, "education_mode");
  if (!isEducationMode(educationMode)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    id: requireString(record, "id"),
    slug: requireString(record, "slug"),
    organizationType: requireString(record, "organization_type"),
    status: requireString(record, "status"),
    branding: {
      displayName: requireString(branding, "display_name"),
      primaryColor: requireString(branding, "primary_color"),
      secondaryColor: requireString(branding, "secondary_color"),
      logo: parseLogo(branding.logo),
    },
    configuration: {
      locale: requireString(configuration, "locale"),
      timezone: requireString(configuration, "timezone"),
      educationMode,
      customDomain: parseCustomDomain(configuration.custom_domain),
      ownidTenantReference: nullableString(
        configuration,
        "ownid_tenant_reference",
      ),
      ownidClientReference: nullableString(
        configuration,
        "ownid_client_reference",
      ),
    },
  };
}

export interface CampusView {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly active: boolean;
}

export function parseCampus(value: unknown): CampusView {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const code = asString(record?.code);
  const name = asString(record?.name);
  const active = asBoolean(record?.active);
  if (!id || !code || !name || active === undefined) {
    throw new Error("The campus response is not supported.");
  }
  return { id, code, name, active };
}
