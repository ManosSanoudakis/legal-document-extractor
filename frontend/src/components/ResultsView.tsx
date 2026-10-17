import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { exportDeed, validate } from "../api";
import { deedData, getPath, setPath } from "../deed";
import { area, DEED_TYPES, deedType, downloadJson, fieldLabel, price, text } from "../format";
import type { ExtractionResult, Source, ValidationIssue } from "../types";
import { Alert, Button, Cell, Empty, FieldGrid, Icon, SectionTitle, Spinner, Stat, Table, Tabs, cx } from "./ui";

type Tab = "parties" | "property" | "notary" | "sources" | "json";
type Kind = "text" | "number" | "deedType";

/** Shared by every value on the page: current data, edit mode, sources and failed checks. */
interface DeedContextValue {
  deed: ExtractionResult;
  editing: boolean;
  update: (path: string, value: unknown) => void;
  sourceFor: (path: string) => Source | undefined;
  issueFor: (path: string) => ValidationIssue | undefined;
  onShowPage?: (page: number) => void;
}

const DeedContext = createContext<DeedContextValue | null>(null);

function useDeed(): DeedContextValue {
  const ctx = useContext(DeedContext);
  if (!ctx) throw new Error("useDeed outside ResultsView");
  return ctx;
}

/** "185.000,50" or "185000.5" → number; empty → null; anything else stays text (and fails validation). */
function parseNumber(input: string): number | string | null {
  const s = input.trim();
  if (!s) return null;
  const normalised = s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : s;
  const n = Number(normalised.replace(/[^\d.-]/g, ""));
  return Number.isFinite(n) && /\d/.test(s) ? n : s;
}

const inputClass =
  "w-full min-w-28 rounded-md border border-stone-300 bg-white px-2 py-1 text-sm font-normal text-ink-900 outline-none " +
  "focus:border-accent-600 focus:ring-2 focus:ring-accent-600/20 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100";

/** One extracted value: shown with its source page, flagged if a check failed, editable in edit mode. */
function Value({ path, kind = "text", format }: { path: string; kind?: Kind; format?: (v: unknown) => string }) {
  const { deed, editing, update, sourceFor, issueFor, onShowPage } = useDeed();
  const value = getPath(deed, path);

  if (editing) {
    if (kind === "deedType") {
      return (
        <select
          aria-label={fieldLabel(path)}
          className={inputClass}
          value={text(value)}
          onChange={(e) => update(path, e.target.value || null)}
        >
          <option value="">Not found</option>
          {Object.entries(DEED_TYPES).map(([v, label]) => (
            <option key={v} value={v}>{label}</option>
          ))}
        </select>
      );
    }
    return (
      <input
        aria-label={fieldLabel(path)}
        className={inputClass}
        defaultValue={text(value)}
        onChange={(e) => update(path, kind === "number" ? parseNumber(e.target.value) : e.target.value.trim() || null)}
      />
    );
  }

  const shown = format ? format(value) : text(value);
  const issue = issueFor(path);
  const source = sourceFor(path);
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5 gap-y-2">
      <span
        title={issue?.message}
        className={cx(
          issue && "underline decoration-wavy decoration-1 underline-offset-4",
          issue?.severity === "error" ? "decoration-red-500" : issue && "decoration-amber-500",
        )}
      >
        {shown || <Empty />}
      </span>
      {source && <SourceLink source={source} onShowPage={onShowPage} />}
    </span>
  );
}

function SourceLink({ source, onShowPage }: { source: Source; onShowPage?: (page: number) => void }) {
  const label = source.page ? `p. ${source.page}` : "source";
  const title = source.quote ? `“${source.quote}”` : undefined;
  const style =
    "whitespace-nowrap rounded px-1 font-sans text-[11px] font-medium leading-4 text-accent-700 ring-1 ring-inset " +
    "ring-accent-200 dark:text-accent-300 dark:ring-accent-800";
  if (!source.page || !onShowPage) {
    return <span className={style} title={title}>{label}</span>;
  }
  const page = source.page;
  return (
    <button
      type="button"
      title={title ? `${title}\nShow page ${page}` : `Show page ${page}`}
      onClick={() => onShowPage(page)}
      className={cx(style, "hover:bg-accent-50 dark:hover:bg-accent-950")}
    >
      {label}
    </button>
  );
}

const partyColumns = (role: "sellers" | "buyers") => [
  { header: "Name", cell: (_: unknown, i: number) => <Value path={`${role}[${i}].full_name`} />, className: "font-medium" },
  { header: "Tax ID (ΑΦΜ)", cell: (_: unknown, i: number) => <Value path={`${role}[${i}].tax_id`} />, className: "font-mono text-xs" },
  { header: "ID document", cell: (_: unknown, i: number) => <Value path={`${role}[${i}].id_document`} />, className: "whitespace-nowrap" },
  { header: "Address", cell: (_: unknown, i: number) => <Value path={`${role}[${i}].address`} /> },
];

const repColumns = [
  { header: "Name", cell: (_: unknown, i: number) => <Value path={`legal_representatives[${i}].full_name`} />, className: "font-medium" },
  { header: "Represents", cell: (_: unknown, i: number) => <Value path={`legal_representatives[${i}].represents`} /> },
  { header: "Tax ID (ΑΦΜ)", cell: (_: unknown, i: number) => <Value path={`legal_representatives[${i}].tax_id`} />, className: "font-mono text-xs" },
  { header: "ID document", cell: (_: unknown, i: number) => <Value path={`legal_representatives[${i}].id_document`} />, className: "whitespace-nowrap" },
];

export function ResultsView({
  result,
  onShowPage,
}: {
  result: ExtractionResult;
  onShowPage?: (page: number) => void;
}) {
  const [tab, setTab] = useState<Tab>("parties");
  const [deed, setDeed] = useState<ExtractionResult>(result);
  const [issues, setIssues] = useState<ValidationIssue[] | undefined>(result._validation);
  const [editing, setEditing] = useState(false);
  const [edited, setEdited] = useState(false);
  const [checking, setChecking] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // Re-check the data shortly after the user stops typing
  useEffect(() => {
    if (!edited) return;
    setChecking(true);
    const timer = setTimeout(() => {
      validate(deedData(deed))
        .then(setIssues)
        .catch(() => undefined)
        .finally(() => setChecking(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [deed, edited]);

  function update(path: string, value: unknown) {
    setDeed((d) => setPath(d, path, value));
    setEdited(true);
  }

  function reset() {
    setDeed(result);
    setIssues(result._validation);
    setEdited(false);
    setEditing(false);
  }

  async function download(format: "xlsx" | "csv") {
    setExportError(null);
    try {
      await exportDeed(deedData(deed), format);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    }
  }

  const sources = deed.sources ?? [];
  const ctx: DeedContextValue = {
    deed,
    editing,
    update,
    sourceFor: (path) => sources.find((s) => s.field === path),
    issueFor: (path) => issues?.find((i) => i.field === path),
    onShowPage,
  };
  const prop = deed.property ?? {};
  const txn = deed.transaction ?? {};
  const sellers = deed.sellers ?? [];
  const buyers = deed.buyers ?? [];
  const reps = deed.legal_representatives ?? [];
  const meta = result._meta;
  const current = { ...deedData(deed), _validation: issues, _meta: meta };

  return (
    <DeedContext.Provider value={ctx}>
      <div className="space-y-5">
        {result._error && (
          <Alert tone="warning">
            The model's response was not valid JSON, so the fields are empty. Details: {result._error}
          </Alert>
        )}

        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Stat label="Deed type" value={deedType(txn.deed_type)} />
          <Stat label="Price" value={price(txn.price)} />
          <Stat label="Date" value={text(txn.date)} />
          <Stat label="Area" value={area(prop.area_sqm)} />
        </div>
        <Checks issues={issues} checking={checking} />

        <div className="flex flex-wrap items-center justify-between gap-3">
          {meta && (
            <p className="text-xs text-ink-500 dark:text-stone-400">
              {meta.model} · {meta.pages} page{meta.pages === 1 ? "" : "s"}{meta.text_layer ? " · text checked" : ""} · {meta.elapsed_seconds} s
              {edited && " · edited"}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {edited && (
              <Button variant="secondary" onClick={reset}>
                Undo edits
              </Button>
            )}
            <Button variant="secondary" onClick={() => setEditing((e) => !e)} aria-pressed={editing}>
              {editing ? <Icon name="check" /> : null}
              {editing ? "Done editing" : "Edit values"}
            </Button>
            <Button variant="secondary" onClick={() => download("xlsx")}>
              <Icon name="download" /> Excel
            </Button>
            <Button variant="secondary" onClick={() => download("csv")}>
              <Icon name="download" /> CSV
            </Button>
          </div>
        </div>
        {exportError && <Alert tone="error">{exportError}</Alert>}

        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: "parties", label: `Parties (${sellers.length + buyers.length})` },
            { id: "property", label: "Property" },
            { id: "notary", label: "Notary" },
            { id: "sources", label: `Sources (${sources.length})` },
            { id: "json", label: "JSON" },
          ]}
        />

        {tab === "parties" && (
          <div className="space-y-5">
            <div>
              <SectionTitle count={sellers.length}>Sellers</SectionTitle>
              <Table columns={partyColumns("sellers")} rows={sellers} empty="No sellers found." />
            </div>
            <div>
              <SectionTitle count={buyers.length}>Buyers</SectionTitle>
              <Table columns={partyColumns("buyers")} rows={buyers} empty="No buyers found." />
            </div>
            {reps.length > 0 && (
              <div>
                <SectionTitle count={reps.length}>Legal representatives</SectionTitle>
                <Table columns={repColumns} rows={reps} empty="" />
              </div>
            )}
          </div>
        )}

        {tab === "property" && (
          <div className="space-y-5">
            <FieldGrid
              fields={[
                ["Type", <Value path="property.type" />],
                ["Floor", <Value path="property.floor" />],
                ["Area", <Value path="property.area_sqm" kind="number" format={area} />],
                ["Municipal unit", <Value path="property.municipal_unit" />],
                ["Address", <Value path="property.address" />],
                ["Price", <Value path="transaction.price" kind="number" format={price} />],
                ["Deed type", <Value path="transaction.deed_type" kind="deedType" format={deedType} />],
                ["Date (YYYY-MM-DD)", <Value path="transaction.date" />],
              ]}
            />
            <div className="border-t border-stone-100 pt-5 dark:border-stone-800">
              <SectionTitle>Land registry</SectionTitle>
              <FieldGrid
                fields={[
                  ["ΚΑΕΚ", <Value path="property.kaek" />],
                  ["Building permit", <Value path="property.building_permit" />],
                ]}
              />
            </div>
          </div>
        )}

        {tab === "notary" && (
          <FieldGrid
            fields={[
              ["Notary", <Value path="notary.name" />],
              ["Location", <Value path="notary.location" />],
              ["Registry number", <Value path="notary.registry_number" />],
            ]}
          />
        )}

        {tab === "sources" && (
          <div className="space-y-3">
            <p className="text-sm text-ink-600 dark:text-stone-400">
              The exact text the model read for each value. Click a page number to show it in the preview.
            </p>
            <Table
              rows={sources}
              empty="The model did not return any sources."
              columns={[
                { header: "Field", cell: (s) => fieldLabel(s.field), className: "whitespace-nowrap" },
                {
                  header: "Page",
                  cell: (s) => (s.page ? <SourceLink source={{ ...s, quote: null }} onShowPage={onShowPage} /> : <Cell value={null} />),
                },
                { header: "Quote", cell: (s) => <Cell value={s.quote} /> },
              ]}
            />
          </div>
        )}

        {tab === "json" && <JsonPanel data={current} filename="extracted_legal_data.json" />}
      </div>
    </DeedContext.Provider>
  );
}

export function JsonPanel({ data, filename }: { data: unknown; filename: string }) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(data, null, 2);

  async function copy() {
    await navigator.clipboard.writeText(json);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Button variant="secondary" onClick={copy}>
          <Icon name={copied ? "check" : "copy"} />
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button variant="secondary" onClick={() => downloadJson(data, filename)}>
          <Icon name="download" />
          Download
        </Button>
      </div>
      <pre className="max-h-[480px] overflow-auto rounded-xl bg-stone-900 p-4 font-mono text-xs leading-relaxed text-stone-100 ring-1 ring-stone-800">
        {json}
      </pre>
    </div>
  );
}

/** Results of the automatic sanity checks run on the extracted data. */
function Checks({ issues, checking }: { issues: ValidationIssue[] | undefined; checking: boolean }) {
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
  const hasErrors = issues.some((i) => i.severity === "error");
  return (
    <Alert tone={hasErrors ? "error" : "warning"}>
      <p className="font-semibold">
        {issues.length} {issues.length === 1 ? "value needs" : "values need"} checking against the document
        {status}
      </p>
      <ul className="mt-1.5 space-y-1">
        {issues.map((issue, i) => (
          <li key={i}>
            <span className="font-medium">{fieldLabel(issue.field)}</span>
            {issue.value !== null && issue.value !== undefined && (
              <span className="font-mono text-xs"> {text(issue.value)}</span>
            )}
            : {issue.message}
          </li>
        ))}
      </ul>
    </Alert>
  );
}
