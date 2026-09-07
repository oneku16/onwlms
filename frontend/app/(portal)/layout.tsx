import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { getSession } from "@/lib/api/auth";

export default async function PortalLayout({
  children,
}: {
  readonly children: ReactNode;
}) {
  const session = await getSession();
  if (!session.authenticated) {
    redirect("/sign-in");
  }
  return <AppShell session={session}>{children}</AppShell>;
}
