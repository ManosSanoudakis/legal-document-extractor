import { useRef, useState, type DragEvent } from "react";
import { createJob, exportBatch, getJobResult, recheck, waitForJob } from "../api";
import { deedType, price } from "../format";
import { remember, useHistoryStore } from "../history";
import type { AppConfig, Deed, ExtractionResult, Job, JobDocument } from "../types";
import { ResultsView } from "./ResultsView";
import { Alert, Badge, Button, Cell, Icon, Spinner, Table, cx } from "./ui";

export const STAGE_LABELS: Record<JobDocument["status"], string> = {
  queued: "Waiting",
  reading: "Reading pages",
  extracting: "Waiting for Gemini",
  done: "Done",
  error: "Failed",
};

/** Many PDFs in one background job: a progress table, each result on demand, one export for all. */
export function BatchView({ config, model, apiKey }: { config: AppConfig; model: string; apiKey: string }) {
  const [files, setFiles] = useState<File[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [jobFiles, setJobFiles] = useState<File[]>([]); // the files of the current job, in its order
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ExtractionResult>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  // The user's corrections and checked fields, by document id; the export uses the corrections
  const [edits, setEdits] = useState<Record<string, Deed>>({});
  const [checked, setChecked] = useState<Record<string, string[]>>({});

  const running = job?.status === "running";
  const history = useHistoryStore();
  // In browser history, each finished deed is saved here (the server saves them itself otherwise)
  const saving = useRef<Set<string>>(new Set());

  function keepInBrowser(current: Job) {
    if (history.kind !== "browser") return;
    for (const doc of current.documents) {
      if (doc.status !== "done" || saving.current.has(doc.id)) continue;
      saving.current.add(doc.id);
      getJobResult(current.id, doc.id)
        .then((result) => remember(history, doc.filename, result))
        .then((result) => setResults((r) => ({ ...r, [doc.id]: result })))
        .catch(() => saving.current.delete(doc.id));
    }
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    const pdfs = [...list].filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    const tooBig = pdfs.filter((f) => f.size > config.max_file_mb * 1024 * 1024);
    const next = [...files, ...pdfs.filter((f) => !tooBig.includes(f))].slice(0, config.max_batch_files);
    setFiles(next);
    setError(
      tooBig.length
        ? `Skipped ${tooBig.map((f) => f.name).join(", ")}: larger than ${config.max_file_mb} MB.`
        : pdfs.length < list.length
          ? "Only PDF files can be added."
          : files.length + pdfs.length > config.max_batch_files
            ? `At most ${config.max_batch_files} files per batch.`
            : null,
    );
  }

  async function start() {
    setError(null);
    setResults({});
    setOpen(null);
    setEdits({});
    setChecked({});
    setJobFiles(files);
    try {
      const created = await createJob(files, apiKey, { task: "extract", model });
      await waitForJob(created, (current) => {
        setJob(current);
        keepInBrowser(current);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the batch");
    }
  }

  async function load(doc: JobDocument): Promise<ExtractionResult | null> {
    if (!job) return null;
    if (results[doc.id]) return results[doc.id];
    const result = await getJobResult(job.id, doc.id);
    setResults((r) => ({ ...r, [doc.id]: result }));
    return result;
  }

  async function toggle(doc: JobDocument) {
    if (open === doc.id) return setOpen(null);
    try {
      await load(doc);
      setOpen(doc.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the result");
    }
  }

  async function download(format: "xlsx" | "csv") {
    if (!job) return;
    setExportError(null);
    try {
      const done = job.documents.filter((d) => d.status === "done");
      const loaded = await Promise.all(done.map((d) => load(d)));
      await exportBatch(
        done.map((d, i) => ({ name: d.filename, deed: edits[d.id] ?? loaded[i]!.deed })),
        format,
      );
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    }
  }

  // The uploaded file for a row, for its second look (same order as the job's documents)
  const fileFor = (doc: JobDocument) => jobFiles[job?.documents.indexOf(doc) ?? -1];
  const done = job?.documents.filter((d) => d.status === "done").length ?? 0;
  const failed = job?.documents.filter((d) => d.status === "error").length ?? 0;
  const openDoc = job?.documents.find((d) => d.id === open);

  return (
    <div className="space-y-5">
      <p className="text-sm text-ink-600 dark:text-stone-400">
        Extract up to {config.max_batch_files} deeds with <strong>{model}</strong>, one after another in the
        background, and download them all as one spreadsheet.
      </p>

      {!job || !running ? (
        <FilePicker files={files} onAdd={addFiles} onRemove={(f) => setFiles(files.filter((x) => x !== f))} />
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={start} disabled={running || files.length === 0 || !apiKey.trim()}>
          {running ? <Spinner /> : <Icon name="play" className="size-3.5 fill-current" />}
          {running ? "Processing…" : `Extract ${files.length || ""} ${files.length === 1 ? "deed" : "deeds"}`}
        </Button>
        {job && (
          <span className="text-sm text-ink-600 dark:text-stone-400">
            {done} of {job.documents.length} done{failed ? ` · ${failed} failed` : ""}
          </span>
        )}
        {job && done > 0 && (
          <div className="ml-auto flex gap-2">
            <Button variant="secondary" onClick={() => download("xlsx")}>
              <Icon name="download" /> Excel (all)
            </Button>
            <Button variant="secondary" onClick={() => download("csv")}>
              <Icon name="download" /> CSV (all)
            </Button>
          </div>
        )}
      </div>
      {!apiKey.trim() && files.length > 0 && <Alert tone="info">Enter your Gemini API key to continue.</Alert>}
      {error && <Alert tone="error">{error}</Alert>}
      {exportError && <Alert tone="error">{exportError}</Alert>}

      {job && (
        <Table
          rows={job.documents}
          empty=""
          columns={[
            { header: "File", cell: (d) => <span className="font-medium">{d.filename}</span> },
            { header: "Status", cell: (d) => <Status doc={d} />, className: "whitespace-nowrap" },
            { header: "Deed type", cell: (d) => <Cell value={d.summary && deedType(d.summary.deed_type)} /> },
            { header: "Price", cell: (d) => <Cell value={d.summary && price(d.summary.price)} />, className: "whitespace-nowrap" },
            {
              header: "To check",
              cell: (d) =>
                d.summary ? (
                  d.summary.flags ? (
                    <span className={d.summary.errors ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300"}>
                      {d.summary.flags}
                    </span>
                  ) : (
                    <Badge tone="success">None</Badge>
                  )
                ) : (
                  <Cell value={null} />
                ),
            },
            {
              header: "",
              cell: (d) =>
                d.status === "done" && (
                  <button type="button" className="text-sm font-medium text-accent-700 hover:underline dark:text-accent-300" onClick={() => toggle(d)}>
                    {open === d.id ? "Close" : "Open"}
                  </button>
                ),
            },
          ]}
        />
      )}

      {openDoc && results[openDoc.id] && (
        <div className="rounded-xl border border-stone-200 p-4 dark:border-stone-800">
          <p className="mb-4 font-semibold">{openDoc.filename}</p>
          <ResultsView
            key={openDoc.id}
            result={results[openDoc.id]}
            saved={{ edited: edits[openDoc.id] ?? null, reviewed: checked[openDoc.id] ?? [] }}
            onChange={(deed) => setEdits((e) => ({ ...e, [openDoc.id]: deed }))}
            onReviewedChange={(fields) => setChecked((c) => ({ ...c, [openDoc.id]: fields }))}
            onRecheck={
              fileFor(openDoc) && apiKey.trim()
                ? (deed, fields) => recheck({ kind: "upload", file: fileFor(openDoc) }, model, apiKey.trim(), deed, fields)
                : undefined
            }
          />
        </div>
      )}
    </div>
  );
}

function Status({ doc }: { doc: JobDocument }) {
  const busy = doc.status === "reading" || doc.status === "extracting";
  return (
    <span
      title={doc.error ?? undefined}
      className={cx(
        "inline-flex items-center gap-1.5",
        doc.status === "error" && "text-red-700 dark:text-red-300",
        doc.status === "queued" && "text-ink-500 dark:text-stone-400",
      )}
    >
      {busy && <Spinner />}
      {doc.status === "done" && <Icon name="check" className="size-3.5 text-emerald-600" />}
      {STAGE_LABELS[doc.status]}
      {doc.elapsed_seconds !== null && doc.status !== "queued" && (
        <span className="tabular-nums text-xs text-ink-500"> · {doc.elapsed_seconds.toFixed(0)} s</span>
      )}
      {doc.status === "error" && doc.error && <span className="text-xs"> · {doc.error}</span>}
    </span>
  );
}

function FilePicker({
  files,
  onAdd,
  onRemove,
}: {
  files: File[];
  onAdd: (files: FileList | null) => void;
  onRemove: (file: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    onAdd(e.dataTransfer.files);
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        role="button"
        tabIndex={0}
        className={cx(
          "cursor-pointer rounded-xl border-2 border-dashed px-4 py-5 text-center transition",
          over
            ? "border-accent-600 bg-accent-50 dark:bg-accent-950/30"
            : "border-stone-300 bg-stone-200/40 hover:border-accent-400 hover:bg-accent-50/60 dark:border-stone-700 dark:bg-stone-800/30",
        )}
      >
        <input
          ref={input}
          type="file"
          multiple
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => {
            onAdd(e.target.files);
            e.target.value = "";
          }}
        />
        <Icon name="upload" className="mx-auto mb-2 size-6 text-ink-400" />
        <p className="text-sm font-semibold">Drop PDFs here or click to browse</p>
      </div>
      {files.length > 0 && (
        <ul className="divide-y divide-stone-100 rounded-xl border border-stone-200 text-sm dark:divide-stone-800 dark:border-stone-800">
          {files.map((f) => (
            <li key={`${f.name}-${f.size}-${f.lastModified}`} className="flex items-center justify-between gap-3 px-4 py-2">
              <span className="truncate">{f.name}</span>
              <button type="button" aria-label={`Remove ${f.name}`} onClick={() => onRemove(f)} className="text-ink-500 hover:text-red-600">
                <Icon name="x" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
