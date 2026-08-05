import Link from "next/link";

import { ErrorState } from "@/components/states";
import { ApiError } from "@/lib/api/errors";
import {
  parseResourceCollection,
  type ResourceCollection,
} from "@/lib/api/resources";
import type { SessionView } from "@/lib/api/session";
import { serverApiRequest } from "@/lib/api/server";

interface DashboardPanelDefinition {
  readonly key: string;
  readonly title: string;
  readonly description: string;
  readonly endpoint: `/api/v1/${string}`;
  readonly href: string;
  readonly tenantScoped?: boolean;
}

interface LoadedDashboardPanel extends DashboardPanelDefinition {
  readonly collection?: ResourceCollection;
  readonly error?: ApiError;
}

function panelDefinitions(
  session: SessionView,
): readonly DashboardPanelDefinition[] {
  const definitions: DashboardPanelDefinition[] = [];
  const add = (definition: DashboardPanelDefinition): void => {
    if (!definitions.some((existing) => existing.key === definition.key)) {
      definitions.push(definition);
    }
  };

  if (session.roles.includes("PlatformAdmin")) {
    add({
      key: "platform-organizations",
      title: "Organizations",
      description: "Current tenant lifecycle overview",
      endpoint: "/api/v1/platform/organizations?limit=5",
      href: "/platform/organizations",
    });
  }

  if (
    session.roles.includes("OrganizationOwner") ||
    session.roles.includes("OrganizationAdmin")
  ) {
    add({
      key: "organization",
      title: "Organization",
      description: "Current tenant configuration",
      endpoint: "/api/v1/organization",
      href: "/organization/branding",
      tenantScoped: true,
    });
    add({
      key: "admissions",
      title: "Admissions",
      description: "Recent application lifecycle activity",
      endpoint: "/api/v1/admissions/applications?limit=5",
      href: "/organization/admissions",
      tenantScoped: true,
    });
    add({
      key: "provisioning",
      title: "Provisioning",
      description: "Retryable activation and integration work",
      endpoint: "/api/v1/operations/provisioning?limit=5",
      href: "/organization/provisioning",
      tenantScoped: true,
    });
  }

  const selfServiceRole = session.roles.find((role) =>
    ["Student", "Teacher", "Guardian"].includes(role),
  );
  if (selfServiceRole) {
    const notificationHref =
      selfServiceRole === "Student"
        ? "/student/notifications"
        : selfServiceRole === "Teacher"
          ? "/teacher/notifications"
          : "/guardian/notifications";
    add({
      key: "notifications",
      title: "Notifications",
      description: "Tenant-scoped updates available to your membership",
      endpoint: "/api/v1/notifications",
      href: notificationHref,
      tenantScoped: true,
    });
  }

  if (session.permissions.includes("provisioning.read")) {
    add({
      key: "operations",
      title: "Operations",
      description: "Tasks made available by your permissions",
      endpoint: "/api/v1/operations/provisioning?limit=5",
      href: "/workspace/operations",
      tenantScoped: true,
    });
  }

  if (session.permissions.includes("academics.structure.manage")) {
    add({
      key: "academic-workspace",
      title: "Academic workspace",
      description: "Records made available by your permissions",
      endpoint: "/api/v1/academics/terms?limit=5",
      href: "/workspace/academics",
      tenantScoped: true,
    });
  }

  return definitions;
}

async function loadPanel(
  definition: DashboardPanelDefinition,
  organizationId: string | undefined,
): Promise<LoadedDashboardPanel> {
  try {
    const collection = await serverApiRequest(
      definition.endpoint,
      parseResourceCollection,
      {
        ...(definition.tenantScoped && organizationId
          ? { organizationId }
          : {}),
      },
    );
    return { ...definition, collection };
  } catch (error) {
    return {
      ...definition,
      error:
        error instanceof ApiError
          ? error
          : new ApiError({
              status: 500,
              code: "dashboard_failed",
              message: "This dashboard panel could not be loaded.",
            }),
    };
  }
}

function DashboardPanel({ panel }: { readonly panel: LoadedDashboardPanel }) {
  if (panel.error) {
    return (
      <article className="dashboard-panel">
        <h2>{panel.title}</h2>
        <ErrorState
          title="Panel unavailable"
          message={
            panel.error.status === 404
              ? "This backend capability is not available in the current release."
              : panel.error.message
          }
          correlationId={panel.error.correlationId}
        />
      </article>
    );
  }
  const collection = panel.collection;
  return (
    <article className="dashboard-panel">
      <div className="dashboard-panel-heading">
        <div>
          <h2>{panel.title}</h2>
          <p>{panel.description}</p>
        </div>
        <span className="metric">
          {collection?.total === null || collection?.total === undefined
            ? "—"
            : collection.total.toLocaleString()}
        </span>
      </div>
      {collection && collection.items.length > 0 ? (
        <ul className="dashboard-list">
          {collection.items.slice(0, 4).map((item) => (
            <li key={item.id}>
              <span>
                <strong>{item.title}</strong>
                {item.subtitle ? <small>{item.subtitle}</small> : null}
              </span>
              {item.status ? (
                <span className="status-pill">{item.status}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="panel-empty">No records are available for this view.</p>
      )}
      <Link className="panel-link" href={panel.href}>
        Open {panel.title.toLowerCase()}
      </Link>
    </article>
  );
}

export async function Dashboard({
  session,
}: {
  readonly session: SessionView;
}) {
  const definitions = panelDefinitions(session);
  const panels = await Promise.all(
    definitions.map((definition) =>
      loadPanel(definition, session.activeOrganization?.id),
    ),
  );
  return (
    <>
      <div className="role-strip" aria-label="Current roles">
        {session.roles.length > 0 ? (
          session.roles.map((role) => (
            <span className="role-chip" key={role}>
              {role.replace(/([a-z])([A-Z])/g, "$1 $2")}
            </span>
          ))
        ) : (
          <span className="role-chip">Permission-based access</span>
        )}
      </div>
      {session.roles.includes("PlatformAdmin") ? (
        <p className="scope-notice">
          Platform administration does not grant permanent access to tenant
          academic records. Tenant panels appear only when a separate active
          membership allows them.
        </p>
      ) : null}
      {panels.length > 0 ? (
        <section className="dashboard-grid" aria-label="Role dashboard panels">
          {panels.map((panel) => (
            <DashboardPanel key={panel.key} panel={panel} />
          ))}
        </section>
      ) : (
        <section className="state-panel">
          <p className="state-kicker">Permission-driven workspace</p>
          <h2>No dashboard panels are available</h2>
          <p>
            Your signed-in identity has no active role or permission that maps
            to a first-release dashboard capability.
          </p>
        </section>
      )}
    </>
  );
}
