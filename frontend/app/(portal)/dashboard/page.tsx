import { Dashboard } from "@/components/dashboard";
import { PageHeader } from "@/components/page-header";
import { getSession } from "@/lib/api/auth";

export const metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const session = await getSession();
  return (
    <>
      <PageHeader
        eyebrow={
          session.activeOrganization?.displayName ??
          (session.roles.includes("PlatformAdmin")
            ? "Platform scope"
            : "Account")
        }
        title={`Welcome, ${session.actor?.displayName ?? "OwnSIS user"}`}
        description="Your workspace combines only the roles, permissions, tenant context, and feature entitlements established by the server session."
      />
      <Dashboard session={session} />
    </>
  );
}
