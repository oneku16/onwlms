"use client";

import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { asRecord, asString } from "@/lib/api/validation";

function parseLoginResponse(value: unknown): string {
  const record = asRecord(value);
  const authorizationUrl = asString(record?.authorization_url);
  if (!authorizationUrl) {
    throw new Error("OwnID did not return an authorization URL.");
  }
  const parsed = new URL(authorizationUrl, window.location.origin);
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new Error("OwnID returned an unsupported authorization URL.");
  }
  return parsed.toString();
}

export function SignInForm() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startLogin(): Promise<void> {
    setSubmitting(true);
    setError(null);
    try {
      const authorizationUrl = await clientApiRequest(
        "/api/v1/auth/login",
        parseLoginResponse,
        {
          method: "POST",
          body: { return_path: "/dashboard" },
          csrfProtection: "not-applicable",
        },
      );
      window.location.assign(authorizationUrl);
    } catch (reason) {
      setError(
        reason instanceof ApiError || reason instanceof Error
          ? reason.message
          : "Sign in could not be started.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div>
      <button
        className="button auth-button"
        type="button"
        onClick={() => void startLogin()}
        disabled={submitting}
      >
        {submitting ? "Opening OwnID…" : "Continue to OwnID"}
      </button>
      {error ? (
        <p className="inline-alert auth-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
