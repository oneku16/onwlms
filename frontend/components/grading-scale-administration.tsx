"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  gradingScaleKinds,
  gradingScaleTemplates,
  parseGradingScale,
  type GradeBandView,
  type GradingScaleView,
} from "@/lib/api/grading";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { decimalValue, optionalTextValue, textValue } from "@/lib/forms";

const maximumBands = 20;

function describeBand(band: GradeBandView): string {
  const gradePoints =
    band.gradePoints === null ? "" : ` · ${band.gradePoints} grade points`;
  return `${band.symbol} from ${band.minimumScore} · ${band.passing ? "passing" : "not passing"}${gradePoints}`;
}

export function GradingScaleAdministration({
  canManage,
  initialScales,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly initialScales: readonly GradingScaleView[];
  readonly organizationId: string;
}) {
  const [scales, setScales] = useState(initialScales);
  const [bandKeys, setBandKeys] = useState<readonly number[]>([0]);
  const [templateSubmitting, setTemplateSubmitting] = useState(false);
  const [templateMessage, setTemplateMessage] = useState<string | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [customSubmitting, setCustomSubmitting] = useState(false);
  const [customMessage, setCustomMessage] = useState<string | null>(null);
  const [customError, setCustomError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function addBand(): void {
    setBandKeys((current) =>
      current.length >= maximumBands
        ? current
        : [...current, Math.max(...current, -1) + 1],
    );
  }

  function removeBand(key: number): void {
    setBandKeys((current) =>
      current.length === 1
        ? current
        : current.filter((candidate) => candidate !== key),
    );
  }

  async function copyTemplate(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setTemplateSubmitting(true);
    setTemplateMessage(null);
    setTemplateError(null);
    try {
      const created = await clientApiRequest(
        "/api/v1/grading/scale-templates",
        parseGradingScale,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            name: textValue(form.get("templateName")),
            template: textValue(form.get("template")),
          },
        },
      );
      setScales((current) => [...current, created]);
      setTemplateMessage(
        `Grading scale “${created.name}” was created from the template.`,
      );
      formElement.reset();
    } catch (caught) {
      setTemplateError(
        caught instanceof ApiError
          ? caught.message
          : "The template grading scale could not be created.",
      );
    } finally {
      setTemplateSubmitting(false);
    }
  }

  async function createCustomScale(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setCustomMessage(null);
    setCustomError(null);
    const minimumScore = decimalValue(form.get("minimumScore"));
    const maximumScore = decimalValue(form.get("maximumScore"));
    if (!minimumScore || !maximumScore) {
      setCustomError(
        "Enter the minimum and maximum scores as decimal numbers.",
      );
      return;
    }
    const bands: {
      minimum_score: string;
      symbol: string;
      passing: boolean;
      grade_points: string | null;
    }[] = [];
    for (const key of bandKeys) {
      const bandMinimum = decimalValue(form.get(`bandMinimum-${key}`));
      const symbol = textValue(form.get(`bandSymbol-${key}`));
      const gradePoints = optionalTextValue(form.get(`bandGradePoints-${key}`));
      if (!bandMinimum || !symbol) {
        setCustomError(
          "Complete the minimum score and symbol of every grade band.",
        );
        return;
      }
      if (gradePoints !== null && decimalValue(gradePoints) === null) {
        setCustomError(
          "Enter grade points as a decimal number or leave empty.",
        );
        return;
      }
      bands.push({
        minimum_score: bandMinimum,
        symbol,
        passing: form.get(`bandPassing-${key}`) === "on",
        grade_points: gradePoints,
      });
    }
    setCustomSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/grading/scales",
        parseGradingScale,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            name: textValue(form.get("name")),
            kind: textValue(form.get("kind")),
            minimum_score: minimumScore,
            maximum_score: maximumScore,
            bands,
          },
        },
      );
      setScales((current) => [...current, created]);
      setCustomMessage(`Grading scale “${created.name}” was created.`);
      setBandKeys([0]);
      formElement.reset();
    } catch (caught) {
      setCustomError(
        caught instanceof ApiError
          ? caught.message
          : "The custom grading scale could not be created.",
      );
    } finally {
      setCustomSubmitting(false);
    }
  }

  const mutationDisabled = !canManage || !csrfAvailable;

  return (
    <div className="notification-layout">
      {scales.length === 0 ? (
        <EmptyState message="No grading scales are available." />
      ) : (
        <section aria-labelledby="grading-scales-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current records</p>
              <h2 id="grading-scales-heading">
                {scales.length.toLocaleString()} grading scale
                {scales.length === 1 ? "" : "s"}
              </h2>
            </div>
          </div>
          <div className="resource-grid">
            {scales.map((scale) => (
              <article className="resource-card" key={scale.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>{scale.name}</h2>
                    <p>
                      Scores {scale.minimumScore} – {scale.maximumScore}
                    </p>
                  </div>
                  <span className="status-pill">{scale.kind}</span>
                </div>
                <dl className="resource-metadata">
                  <div>
                    <dt>Bands</dt>
                    <dd>{scale.bands.map(describeBand).join("; ")}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </section>
      )}
      <form
        className="form-card"
        onSubmit={(event) => void copyTemplate(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Official grading</p>
            <h2>Copy a built-in scale template</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Scale name
            <input name="templateName" required maxLength={255} />
          </label>
          <label>
            Template
            <select name="template" required defaultValue="">
              <option value="" disabled>
                Select a template
              </option>
              {gradingScaleTemplates.map((template) => (
                <option key={template} value={template}>
                  {template}
                </option>
              ))}
            </select>
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={templateError}
          message={templateMessage}
          permissionNotice="Your current membership cannot manage grading scales."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={mutationDisabled || templateSubmitting}
          >
            {templateSubmitting ? "Creating…" : "Create from template"}
          </button>
        </div>
      </form>
      <form
        className="form-card"
        onSubmit={(event) => void createCustomScale(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Official grading</p>
            <h2>Create a custom scale</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Scale name
            <input name="name" required maxLength={255} />
          </label>
          <label>
            Kind
            <select name="kind" required defaultValue="">
              <option value="" disabled>
                Select a kind
              </option>
              {gradingScaleKinds.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label>
            Minimum score
            <input
              name="minimumScore"
              required
              inputMode="decimal"
              pattern="\d+(\.\d+)?"
              maxLength={12}
            />
          </label>
          <label>
            Maximum score
            <input
              name="maximumScore"
              required
              inputMode="decimal"
              pattern="\d+(\.\d+)?"
              maxLength={12}
            />
          </label>
        </div>
        <fieldset disabled={customSubmitting}>
          <legend>Grade bands (at least one, up to {maximumBands})</legend>
          {bandKeys.map((key, index) => (
            <div className="form-grid" key={key}>
              <label>
                Band {index + 1} minimum score
                <input
                  name={`bandMinimum-${key}`}
                  required
                  inputMode="decimal"
                  pattern="\d+(\.\d+)?"
                  maxLength={12}
                />
              </label>
              <label>
                Band {index + 1} symbol
                <input name={`bandSymbol-${key}`} required maxLength={32} />
              </label>
              <label>
                Band {index + 1} grade points (optional)
                <input
                  name={`bandGradePoints-${key}`}
                  inputMode="decimal"
                  pattern="\d+(\.\d+)?"
                  maxLength={12}
                />
              </label>
              <label className="checkbox-label">
                <input name={`bandPassing-${key}`} type="checkbox" />
                Band {index + 1} is passing
              </label>
              <div className="form-actions">
                <button
                  className="button button-secondary button-small"
                  type="button"
                  disabled={bandKeys.length === 1}
                  onClick={() => removeBand(key)}
                >
                  Remove band {index + 1}
                </button>
              </div>
            </div>
          ))}
          <div className="button-row">
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={bandKeys.length >= maximumBands}
              onClick={addBand}
            >
              Add grade band
            </button>
          </div>
        </fieldset>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={customError}
          message={customMessage}
          permissionNotice="Your current membership cannot manage grading scales."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={mutationDisabled || customSubmitting}
          >
            {customSubmitting ? "Creating…" : "Create custom scale"}
          </button>
        </div>
      </form>
    </div>
  );
}
