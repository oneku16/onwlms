import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GradeAmendmentForm } from "@/components/grade-amendment-form";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("GradeAmendmentForm", () => {
  it("submits the optimistic revision number and explanation", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "grade-1" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<GradeAmendmentForm canSubmit organizationId="org-1" />);

    fireEvent.change(screen.getByLabelText("Official grade identifier"), {
      target: { value: "grade-1" },
    });
    fireEvent.change(screen.getByLabelText("Revised raw score"), {
      target: { value: "91.5" },
    });
    fireEvent.change(screen.getByLabelText(/^Current revision number/), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText(/^Amendment explanation/), {
      target: { value: "The source record was corrected." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Record grade revision" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/grading/final-grades/grade-1/revisions");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      raw_score: "91.5",
      explanation: "The source record was corrected.",
      grading_scale_id: null,
      expected_revision_number: 3,
    });
    expect(
      await screen.findByText(
        "The official grade revision was recorded with its explanation.",
      ),
    ).toBeVisible();
  });
});
