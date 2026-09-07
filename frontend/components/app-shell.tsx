"use client";

import type { CSSProperties, ReactNode } from "react";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { AppNavigation } from "@/components/app-navigation";
import { clientApiRequest, readCsrfCookie } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { SessionView } from "@/lib/api/session";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { asRecord, asString, unwrapPayload } from "@/lib/api/validation";

interface AppShellProps {
  readonly session: SessionView;
  readonly children: ReactNode;
}

type BrandStyle = CSSProperties & {
  "--tenant-primary": string;
  "--tenant-accent": string;
};

interface LogoutResponse {
  readonly providerLogoutUrl: string | null;
}

function parseLogout(value: unknown): LogoutResponse {
  const record = asRecord(unwrapPayload(value));
  if (!record || record.logged_out !== true) {
    throw new Error("The logout response is not supported.");
  }
  if (record.provider_logout_url === null) {
    return { providerLogoutUrl: null };
  }
  const providerLogoutUrl = asString(record.provider_logout_url);
  if (!providerLogoutUrl) {
    throw new Error("The logout response is not supported.");
  }
  const parsed = new URL(providerLogoutUrl);
  if (parsed.protocol !== "https:") {
    throw new Error("The provider logout URL is not secure.");
  }
  return { providerLogoutUrl };
}

export function AppShell({ session, children }: AppShellProps) {
  const router = useRouter();
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const [switchingOrganization, setSwitchingOrganization] = useState(false);
  const csrfAvailable = useCsrfProtection();
  const organization = session.activeOrganization;
  const platformAdmin = session.roles.includes("PlatformAdmin");
  const brandStyle: BrandStyle = {
    "--tenant-primary": organization?.branding.primaryColor ?? "#173f5f",
    "--tenant-accent": organization?.branding.accentColor ?? "#f0a43c",
  };

  async function logout(): Promise<void> {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      const result = await clientApiRequest(
        "/api/v1/auth/logout",
        parseLogout,
        {
          method: "POST",
        },
      );
      if (result.providerLogoutUrl) {
        window.location.assign(result.providerLogoutUrl);
        return;
      }
      router.replace("/sign-in");
      router.refresh();
    } catch (error) {
      setLogoutError(
        error instanceof ApiError
          ? error.message
          : "Sign out could not be completed.",
      );
      setLoggingOut(false);
    }
  }

  async function switchOrganization(organizationId: string): Promise<void> {
    if (organizationId === organization?.id) {
      return;
    }
    const csrfToken = readCsrfCookie();
    if (!csrfToken) {
      setLogoutError(
        "The organization context cannot be changed because this session has no CSRF token.",
      );
      return;
    }
    setSwitchingOrganization(true);
    setLogoutError(null);
    try {
      const response = await fetch("/api/organization-context", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken,
        },
        body: JSON.stringify({ organizationId }),
      });
      if (!response.ok) {
        throw new Error("The organization context could not be changed.");
      }
      router.refresh();
    } catch (error) {
      setLogoutError(
        error instanceof Error
          ? error.message
          : "The organization context could not be changed.",
      );
    } finally {
      setSwitchingOrganization(false);
    }
  }

  return (
    <div className="app-shell" style={brandStyle}>
      <aside className="sidebar">
        <div className="brand-block">
          {organization?.branding.logoUrl ? (
            // The URL is restricted by the session adapter to HTTPS or same-origin.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              className="tenant-logo"
              src={organization.branding.logoUrl}
              alt={`${organization.displayName} logo`}
            />
          ) : (
            <span className="tenant-mark" aria-hidden="true">
              {(organization?.displayName ?? "OwnSIS")
                .slice(0, 1)
                .toUpperCase()}
            </span>
          )}
          <div>
            <p className="product-name">OwnSIS</p>
            <p className="tenant-name">
              {organization?.displayName ??
                (platformAdmin ? "Platform administration" : "No membership")}
            </p>
          </div>
        </div>
        {organization ? (
          <div className="tenant-context" aria-label="Active organization">
            <span>Active organization</span>
            {session.memberships.length > 1 ? (
              <label>
                <span className="visually-hidden">Active organization</span>
                <select
                  className="tenant-selector"
                  value={organization.id}
                  onChange={(event) =>
                    void switchOrganization(event.currentTarget.value)
                  }
                  disabled={switchingOrganization || !csrfAvailable}
                >
                  {session.memberships.map((membership) => (
                    <option
                      key={membership.organizationId}
                      value={membership.organizationId}
                    >
                      {membership.organization.displayName}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <strong>{organization.displayName}</strong>
            )}
            <small>
              {switchingOrganization
                ? "Changing context…"
                : `${organization.timezone} · ${organization.locale}`}
            </small>
          </div>
        ) : (
          <div className="tenant-context platform-context">
            <span>Scope</span>
            <strong>
              {platformAdmin ? "Platform only" : "No active organization"}
            </strong>
            <small>
              {platformAdmin
                ? "No tenant academic access is implied."
                : "Ask an administrator to verify your membership."}
            </small>
          </div>
        )}
        <AppNavigation session={session} />
      </aside>

      <div className="mobile-header">
        <div>
          <p className="product-name">OwnSIS</p>
          <strong>
            {organization?.displayName ??
              (platformAdmin ? "Platform" : "No organization")}
          </strong>
        </div>
        <details className="mobile-navigation">
          <summary>Menu</summary>
          <div className="mobile-navigation-panel">
            <AppNavigation label="Mobile navigation" session={session} />
          </div>
        </details>
      </div>

      <div className="workspace">
        <header className="topbar">
          <div className="identity-summary">
            <span className="avatar" aria-hidden="true">
              {session.actor?.displayName.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong>{session.actor?.displayName}</strong>
              <span>
                {session.roles.join(" · ") || "Permission-based access"}
              </span>
            </div>
          </div>
          <button
            className="text-button"
            type="button"
            onClick={() => void logout()}
            disabled={loggingOut || !csrfAvailable}
            title={
              csrfAvailable
                ? undefined
                : "Sign out is unavailable because this session has no CSRF token."
            }
          >
            {loggingOut ? "Signing out…" : "Sign out"}
          </button>
        </header>
        {logoutError ? (
          <p className="inline-alert" role="alert">
            {logoutError}
          </p>
        ) : null}
        <main className="main-content" id="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
