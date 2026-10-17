import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { SAMPLE_URL, demoPdfUrl } from "../api";
import type { AppConfig, DemoDeed, DocumentChoice } from "../types";
import { Alert, Card, CardHeader, Icon, Segmented, cx } from "./ui";

type Source = DocumentChoice["kind"];

export function DocumentCard({
  config,
  document,
  onChange,
  page,
}: {
  config: AppConfig;
  document: DocumentChoice | null;
  onChange: (doc: DocumentChoice | null) => void;
  page?: number | null;
}) {
  const [source, setSource] = useState<Source>(
    document?.kind ?? (config.demos.length ? "demo" : config.sample_available ? "sample" : "upload"),
  );
  const [file, setFile] = useState<File | null>(null);
  const [demo, setDemo] = useState<DemoDeed | undefined>(
    document?.kind === "demo" ? document.demo : config.demos[0],
  );
  const [error, setError] = useState<string | null>(null);

  function selectSource(next: Source) {
    setSource(next);
    setError(null);
    if (next === "demo") onChange(demo ? { kind: "demo", demo } : null);
    else if (next === "sample") onChange({ kind: "sample" });
    else onChange(file ? { kind: "upload", file } : null);
  }

  function selectDemo(next: DemoDeed) {
    setDemo(next);
    onChange({ kind: "demo", demo: next });
  }

  function acceptFile(f: File | undefined) {
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    if (f.size > config.max_file_mb * 1024 * 1024) {
      setError(`That file is larger than ${config.max_file_mb} MB.`);
      return;
    }
    setError(null);
    setFile(f);
    onChange({ kind: "upload", file: f });
  }

  const sources = [
    ...(config.demos.length ? [{ value: "demo" as const, label: "Demo" }] : []),
    ...(config.sample_available ? [{ value: "sample" as const, label: "Sample deed" }] : []),
    { value: "upload" as const, label: "Upload PDF" },
  ];

  return (
    <Card>
      <CardHeader step="2" icon="file" title="Document" subtitle="A demo, the sample deed or your own PDF" />
      <div className="space-y-4 p-5">
        {sources.length > 1 && (
          <Segmented label="Document source" value={source} onChange={selectSource} options={sources} />
        )}

        {source === "demo" ? (
          <DemoPicker demos={config.demos} selected={demo} onSelect={selectDemo} />
        ) : source === "sample" ? (
          <p className="text-sm text-ink-600 dark:text-stone-400">
            A <strong className="font-semibold text-ink-800 dark:text-stone-200">fictional</strong> Greek sale
            deed. Every name, number and address is invented, and its tax IDs are deliberately invalid, so the
            automatic checks will flag them.
          </p>
        ) : (
          <Dropzone file={file} config={config} onFile={acceptFile} />
        )}
        {error && <Alert tone="error">{error}</Alert>}

        {document && <Preview document={document} page={page ?? null} />}
      </div>
    </Card>
  );
}

/** Fictional deeds with a saved model answer: open one to see the results without an API key. */
function DemoPicker({
  demos,
  selected,
  onSelect,
}: {
  demos: DemoDeed[];
  selected: DemoDeed | undefined;
  onSelect: (demo: DemoDeed) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-ink-600 dark:text-stone-400">
        Real Gemini answers for <strong className="font-semibold text-ink-800 dark:text-stone-200">fictional</strong>{" "}
        long deeds, saved from a benchmark run. No API key needed.
      </p>
      <div role="radiogroup" aria-label="Demo deed" className="space-y-2">
        {demos.map((d) => {
          const active = d.id === selected?.id;
          return (
            <button
              key={d.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onSelect(d)}
              className={cx(
                "block w-full rounded-xl border px-3.5 py-2.5 text-left transition",
                active
                  ? "border-accent-600 bg-accent-50 ring-1 ring-accent-600 dark:bg-accent-950/40"
                  : "border-stone-200 hover:border-accent-400 hover:bg-accent-50/50 dark:border-stone-800 dark:hover:bg-stone-800/40",
              )}
            >
              <span className="block text-sm font-semibold text-ink-900 dark:text-stone-100">{d.title}</span>
              <span className="mt-0.5 block text-xs text-ink-600 dark:text-stone-400">{d.description}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Dropzone({
  file,
  config,
  onFile,
}: {
  file: File | null;
  config: AppConfig;
  onFile: (f: File | undefined) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    onFile(e.dataTransfer.files[0]);
  }

  return (
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
        "cursor-pointer rounded-xl border-2 border-dashed px-4 py-6 text-center transition",
        over
          ? "border-accent-600 bg-accent-50 dark:bg-accent-950/30"
          : "border-stone-300 bg-stone-200/40 hover:border-accent-400 hover:bg-accent-50/60 dark:border-stone-700 dark:bg-stone-800/30",
      )}
    >
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          onFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {file ? (
        <>
          <Icon name="file" className="mx-auto mb-2 size-6 text-accent-700 dark:text-accent-400" />
          <p className="truncate text-sm font-semibold">{file.name}</p>
          <p className="mt-1 text-xs text-ink-500">
            {(file.size / 1024 / 1024).toFixed(2)} MB · click or drop to replace
          </p>
        </>
      ) : (
        <>
          <Icon name="upload" className="mx-auto mb-2 size-6 text-ink-400" />
          <p className="text-sm font-semibold">Drop a PDF here or click to browse</p>
          <p className="mt-1 text-xs text-ink-500">
            Up to {config.max_file_mb} MB and {config.max_pages} pages · deleted after processing
          </p>
        </>
      )}
    </div>
  );
}

function Preview({ document, page }: { document: DocumentChoice; page: number | null }) {
  const objectUrl = useMemo(
    () => (document.kind === "upload" ? URL.createObjectURL(document.file) : null),
    [document],
  );
  useEffect(() => () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  }, [objectUrl]);

  const src = objectUrl ?? (document.kind === "demo" ? demoPdfUrl(document.demo.id) : SAMPLE_URL);
  return (
    <div className="overflow-hidden rounded-xl border border-stone-200 dark:border-stone-800">
      {/* key forces a reload so the browser PDF viewer jumps to the new page */}
      <iframe
        id="document-preview"
        key={page ?? 0}
        title="Document preview"
        src={`${src}#${page ? `page=${page}&` : ""}view=FitH`}
        className="h-[520px] w-full bg-stone-100 lg:h-[640px]" />
    </div>
  );
}
