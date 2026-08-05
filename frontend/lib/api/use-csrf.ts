"use client";

import { useSyncExternalStore } from "react";

import { readCsrfCookie } from "@/lib/api/client";

export function useCsrfProtection(): boolean {
  return useSyncExternalStore(
    () => () => undefined,
    () => readCsrfCookie() !== null,
    () => false,
  );
}
