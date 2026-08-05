"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { SessionView } from "@/lib/api/session";
import { visibleNavigation } from "@/lib/navigation";

interface AppNavigationProps {
  readonly session: SessionView;
  readonly pathname?: string;
  readonly label?: string;
}

export function AppNavigation({
  session,
  pathname,
  label = "Primary navigation",
}: AppNavigationProps) {
  const detectedPathname = usePathname();
  const currentPathname = pathname ?? detectedPathname;
  const sections = visibleNavigation(session);

  return (
    <nav className="app-navigation" aria-label={label}>
      {sections.map((section) => (
        <section className="navigation-section" key={section.label}>
          <h2>{section.label}</h2>
          <ul>
            {section.items.map((item) => {
              const active =
                currentPathname === item.href ||
                (item.href !== "/dashboard" &&
                  currentPathname.startsWith(`${item.href}/`));
              return (
                <li key={item.href}>
                  <Link
                    aria-current={active ? "page" : undefined}
                    className={
                      active ? "navigation-link active" : "navigation-link"
                    }
                    data-unavailable={item.unavailable ? "true" : undefined}
                    href={item.href}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </nav>
  );
}
