import {
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
} from "@/lib/api/validation";

export interface AcademicEnrollmentChoice {
  readonly id: string;
  readonly studentId: string;
  readonly programId: string;
  readonly status: string;
}

export interface GradingScaleChoice {
  readonly id: string;
  readonly name: string;
}

export interface TranscriptGradeChoice {
  readonly finalGradeId: string;
  readonly courseId: string;
  readonly courseOfferingId: string;
  readonly termId: string;
  readonly symbol: string;
}

export interface FinalGradeMutationResult {
  readonly id: string;
  readonly revisionNumber: number;
}

function requireArray(value: unknown, contract: string): readonly unknown[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return payload;
}

export function parseAcademicEnrollmentChoices(
  value: unknown,
): readonly AcademicEnrollmentChoice[] {
  return requireArray(value, "academic enrollment").map((entry) => {
    const record = asRecord(entry);
    const id = asString(record?.id);
    const studentId = asString(record?.student_id);
    const programId = asString(record?.program_id);
    const status = asString(record?.status);
    if (!id || !studentId || !programId || !status) {
      throw new Error("The academic enrollment response is not supported.");
    }
    return { id, studentId, programId, status };
  });
}

export function parseGradingScaleChoices(
  value: unknown,
): readonly GradingScaleChoice[] {
  return requireArray(value, "grading scale").map((entry) => {
    const record = asRecord(entry);
    const id = asString(record?.id);
    const name = asString(record?.name);
    if (!id || !name) {
      throw new Error("The grading scale response is not supported.");
    }
    return { id, name };
  });
}

export function parseTranscriptGradeChoices(
  value: unknown,
): readonly TranscriptGradeChoice[] {
  return requireArray(value, "official transcript").map((entry) => {
    const record = asRecord(entry);
    const finalGradeId = asString(record?.final_grade_id);
    const courseId = asString(record?.course_id);
    const courseOfferingId = asString(record?.course_offering_id);
    const termId = asString(record?.term_id);
    const symbol = asString(record?.symbol);
    if (!finalGradeId || !courseId || !courseOfferingId || !termId || !symbol) {
      throw new Error("The official transcript response is not supported.");
    }
    return { finalGradeId, courseId, courseOfferingId, termId, symbol };
  });
}

export function parseCurrentRevisionNumber(value: unknown): number {
  const revisions = requireArray(value, "grade revision history").map(
    (entry) => {
      const record = asRecord(entry);
      const revisionNumber = asNumber(record?.revision_number);
      if (
        revisionNumber === undefined ||
        !Number.isInteger(revisionNumber) ||
        revisionNumber < 1
      ) {
        throw new Error(
          "The grade revision history response is not supported.",
        );
      }
      return revisionNumber;
    },
  );
  return revisions.length === 0 ? 0 : Math.max(...revisions);
}

export function parseFinalGradeMutation(
  value: unknown,
): FinalGradeMutationResult {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const revisionNumber = asNumber(record?.revision_number);
  if (
    !id ||
    revisionNumber === undefined ||
    !Number.isInteger(revisionNumber) ||
    revisionNumber < 0
  ) {
    throw new Error("The final-grade response is not supported.");
  }
  return { id, revisionNumber };
}
