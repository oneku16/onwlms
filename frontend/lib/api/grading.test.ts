import { describe, expect, it } from "vitest";

import { parseGradingScale, parseGradingScales } from "@/lib/api/grading";

const scale = {
  id: "scale-1",
  name: "Undergraduate percentage",
  kind: "percentage",
  minimum_score: "0.00",
  maximum_score: "100.00",
  bands: [
    {
      minimum_score: "60.00",
      symbol: "Pass",
      passing: true,
      grade_points: "4.0",
    },
    {
      minimum_score: "0.00",
      symbol: "Fail",
      passing: false,
      grade_points: null,
    },
  ],
};

describe("grading scale contract", () => {
  it("parses scales with decimal-string bands and nullable grade points", () => {
    expect(parseGradingScales([scale])).toEqual([
      {
        id: "scale-1",
        name: "Undergraduate percentage",
        kind: "percentage",
        minimumScore: "0.00",
        maximumScore: "100.00",
        bands: [
          {
            minimumScore: "60.00",
            symbol: "Pass",
            passing: true,
            gradePoints: "4.0",
          },
          {
            minimumScore: "0.00",
            symbol: "Fail",
            passing: false,
            gradePoints: null,
          },
        ],
      },
    ]);
  });

  it("rejects unknown kinds and band-less scales", () => {
    expect(() => parseGradingScale({ ...scale, kind: "stars" })).toThrow(
      "The grading scale response is not supported.",
    );
    expect(() => parseGradingScale({ ...scale, bands: [] })).toThrow(
      "The grading scale response is not supported.",
    );
  });
});
