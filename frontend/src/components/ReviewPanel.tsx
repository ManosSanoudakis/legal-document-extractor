import { useState, type ReactNode } from "react";
import { isNumberField, parseNumber, tryGetPath } from "../deed";
import { fieldLabel, text } from "../format";
import type { ExtractionResult, RecheckAnswer, ValidationIssue } from "../types";
import { Alert, Badge, Button, Icon, Spinner, cx } from "./ui";

/** Paths of single fields ("property.kaek", "sellers[0].tax_id"), the only ones a second look can read. */
const FIELD_PATH = /^\w+(\[\d+\])?\.\w+$/;

/** Failed checks grouped by field, in the order they were reported. */
function byField(issues: ValidationIssue[]): [field: string, issues: ValidationIssue[]][] {
  const groups = new Map<string, ValidationIssue[]>();
  for (const issue of issues) groups.set(issue.field, [...(groups.get(issue.field) ?? []), issue]);
  return [...groups];
}

/**
 * The values a person should check, as a to-do list: each flagged field with why it was flagged,
 * a "checked" tick, and optionally a second, independent reading of the field at higher resolution.
 */
export function ReviewPanel({
  deed,
  issues,
  checking,
  reviewed,
  onToggleReviewed,
  onUse,
  onRecheck,
}: {
  deed: ExtractionResult;
  issues: ValidationIssue[] | undefined;
  checking: boolean;
  reviewed: Set<string>;
  onToggleReviewed: (field: string) => void;
  onUse: (field: string, value: unknown) => void;
  /** Absent when the PDF is not at hand (e.g. a result opened from history). */
  onRecheck?: (fields: string[]) => Promise<RecheckAnswer[]>;
}) {
  const [answers, setAnswers] = useState<Record<string, RecheckAnswer>>({});
  const [rechecking, setRechecking] = useState(false);
  const [recheckError, setRecheckError] = useState<string | null>(null);

  if (!issues) return null;
  const status: ReactNode = checking && (
    <span className="ml-2 inline-flex items-center gap-1.5 text-xs font-normal opacity-75">
      <Spinner /> Re-checking
    </span>
  );
  if (issues.length === 0) {
    return (
      <Alert tone="info">
        All automatic checks passed: tax IDs, ΚΑΕΚ format, date, amounts and source quotes.{status}
      </Alert>
    );
  }

  const groups = byField(issues);
  const done = groups.filter(([field]) => reviewed.has(field)).length;
  const readable = groups.map(([field]) => field).filter((f) => FIELD_PATH.test(f) && !reviewed.has(f));
  const hasErrors = issues.some((i) => i.severity === "error");

  async function secondLook() {
    if (!onRecheck) return;
    setRechecking(true);
    setRecheckError(null);
    try {
      const found = await onRecheck(readable);
      setAnswers((prev) => ({ ...prev, ...Object.fromEntries(found.map((a) => [a.field, a])) }));
    } catch (err) {
      setRecheckError(err instanceof Error ? err.message : "Second look failed");
    } finally {
      setRechecking(false);
    }
  }

  return (
    <Alert tone={done === groups.length ? "info" : hasErrors ? "error" : "warning"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">
          {done === groups.length
            ? `All ${groups.length} flagged ${groups.length === 1 ? "value" : "values"} checked`
            : `${groups.length} ${groups.length === 1 ? "value needs" : "values need"} checking · ${done} done`}
          {status}
        </p>
        {onRecheck && readable.length > 0 && (
          <Button
            variant="secondary"
            onClick={secondLook}
            disabled={rechecking}
            title="Read these fields again at higher resolution, without showing the model its first answer (1 request)"
          >
            {rechecking ? <Spinner /> : <Icon name="play" className="size-3 fill-current" />} Second look
          </Button>
        )}
      </div>
      {recheckError && <p className="mt-1.5 text-xs">{recheckError}</p>}

      <ul className="mt-2 space-y-2">
        {groups.map(([field, fieldIssues]) => {
          const done = reviewed.has(field);
          const answer = answers[field];
          const current = tryGetPath(deed, field);
          return (
            <li key={field} className={cx("flex items-start gap-2.5", done && "opacity-60")}>
              <input
                type="checkbox"
                className="mt-1 accent-current"
                checked={done}
                onChange={() => onToggleReviewed(field)}
                aria-label={`Mark ${fieldLabel(field)} as checked`}
              />
              <div className="min-w-0 flex-1">
                <span className="font-medium">{fieldLabel(field)}</span>
                {current !== null && current !== undefined && (
                  <span className="font-mono text-xs"> {text(current)}</span>
                )}
                : {fieldIssues.map((i) => i.message).join(" ")}
                {answer && !done && (
                  <SecondLook
                    answer={answer}
                    onUse={() => onUse(field, isNumberField(field) ? parseNumber(answer.value ?? "") : answer.value)}
                  />
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Alert>
  );
}

function SecondLook({ answer, onUse }: { answer: RecheckAnswer; onUse: () => void }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
      <span>
        Second look: <span className="font-mono">{answer.value ?? "not found"}</span>
        {answer.page ? ` (p. ${answer.page})` : ""}
      </span>
      <Badge tone={answer.agrees ? "success" : "error"}>{answer.agrees ? "Same" : "Different"}</Badge>
      {answer.found_in_text === false && <span>Not in the PDF's text either.</span>}
      {!answer.agrees && answer.value !== null && (
        <button type="button" onClick={onUse} className="font-medium underline underline-offset-2">
          Use this value
        </button>
      )}
    </div>
  );
}
