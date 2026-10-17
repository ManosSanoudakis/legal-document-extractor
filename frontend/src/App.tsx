import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, evaluate, extract, getConfig, recheck } from "./api";
import { DocumentCard } from "./components/DocumentCard";
import { EvaluationView } from "./components/EvaluationView";
import { ResultsView } from "./components/ResultsView";
import { SettingsCard } from "./components/SettingsCard";
import { Alert, Button, Card, Icon, Spinner, Tabs } from "./components/ui";
import type { AppConfig, DocumentChoice, EvaluationReport, ExtractionResult } from "./types";

type Task<T> =
  | { status: "idle" }
  | { status: "running"; startedAt: number }
  | { status: "done"; data: T }
  | { status: "error"; message: string };

/** Run an async job, tracking loading/error state; ignores results of stale runs. */
function useTask<T>() {
  const [task, setTask] = useState<Task<T>>({ status: "idle" });
  const runId = useRef(0);

  async function run(job: () => Promise<T>) {
    const id = ++runId.current;
    setTask({ status: "running", startedAt: Date.now() });
    try {
      const data = await job();
      if (id === runId.current) setTask({ status: "done", data });
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Unexpected error";
      if (id === runId.current) setTask({ status: "error", message });
    }
  }

  function reset() {
    runId.current++;
    setTask({ status: "idle" });
  }

  return { task, run, reset };
}

function useElapsed(startedAt: number | null): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? 0 : Math.max(0, (now - startedAt) / 1000);
}

type View = "extract" | "evaluate";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [doc, setDoc] = useState<DocumentChoice | null>(null);
  const [view, setView] = useState<View>("extract");
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const extraction = useTask<ExtractionResult>();
  const evaluation = useTask<EvaluationReport>();

  useEffect(() => {
    getConfig()
      .then((c) => {
        setConfig(c);
        setModel(c.models[0]);
        setDoc(c.sample_available ? { kind: "sample" } : null);
      })
      .catch((err: Error) => setConfigError(err.message));
  }, []);

  /** Jump the PDF preview to a page and bring it into view. */
  function showPage(page: number) {
    setPreviewPage(page);
    document.getElementById("document-preview")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function changeDocument(next: DocumentChoice | null) {
    setDoc(next);
    setPreviewPage(null);
    extraction.reset();
    evaluation.reset();
  }

  const missing = !doc
    ? "Choose the sample deed or upload a PDF."
    : !apiKey.trim()
      ? "Enter your Gemini API key to continue."
      : null;

  return (
    <div className="min-h-screen">
      <Header />

      <main className="mx-auto max-w-7xl px-4 pb-16 sm:px-6 lg:px-8">
        {configError && (
          <Alert tone="error">
            Could not load settings from the API: {configError}
          </Alert>
        )}
        {!config && !configError && (
          <p className="flex items-center gap-2 text-sm text-ink-500">
            <Spinner /> Connecting to the API…
          </p>
        )}

        {config && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <div className="space-y-6 lg:col-span-5">
              <SettingsCard
                apiKey={apiKey}
                onApiKeyChange={setApiKey}
                models={config.models}
                model={model}
                onModelChange={setModel}
              />
              <DocumentCard config={config} document={doc} onChange={changeDocument} page={previewPage} />
            </div>

            <Card className="lg:col-span-7">
              <div className="px-5 pt-2">
                <Tabs
                  active={view}
                  onChange={setView}
                  tabs={[
                    { id: "extract", label: "Extraction", icon: "doc" },
                    { id: "evaluate", label: "Model evaluation", icon: "chart" },
                  ]}
                />
              </div>
              <div className="p-5">
                {view === "extract" ? (
                  <RunPanel
                    intro={
                      <>
                        Send every page to <strong>{model}</strong> and turn the deed into structured data.
                      </>
                    }
                    label={`Extract with ${model.replace("gemini-", "")}`}
                    runningLabel="Reading the document…"
                    missing={missing}
                    task={extraction.task}
                    onRun={() => doc && extraction.run(() => extract(doc, model, apiKey.trim()))}
                    render={(data) => (
                      <ResultsView
                        result={data}
                        onShowPage={showPage}
                        onRecheck={
                          doc && apiKey.trim()
                            ? (deed, fields) => recheck(doc, data._meta?.model ?? model, apiKey.trim(), deed, fields)
                            : undefined
                        }
                      />
                    )}
                  />
                ) : (
                  <RunPanel
                    intro={
                      <>
                        Run <strong>{config.models.join(" and ")}</strong> on the same document and compare their
                        accuracy, completeness and speed.
                      </>
                    }
                    label="Run evaluation"
                    runningLabel="Running both models. This can take a minute…"
                    missing={missing}
                    task={evaluation.task}
                    onRun={() => doc && evaluation.run(() => evaluate(doc, apiKey.trim()))}
                    render={(data) => <EvaluationView report={data} />}
                  />
                )}
              </div>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}

function RunPanel<T>({
  intro,
  label,
  runningLabel,
  missing,
  task,
  onRun,
  render,
}: {
  intro: ReactNode;
  label: string;
  runningLabel: string;
  missing: string | null;
  task: Task<T>;
  onRun: () => void;
  render: (data: T) => ReactNode;
}) {
  const running = task.status === "running";
  const elapsed = useElapsed(running ? task.startedAt : null);

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink-600 dark:text-stone-400">{intro}</p>
        <Button onClick={onRun} disabled={running || missing !== null} className="shrink-0">
          {running ? <Spinner /> : <Icon name="play" className="size-3.5 fill-current" />} {label}
        </Button>
      </div>
      {missing && !running && <Alert tone="info">{missing}</Alert>}

      {running && (
        <div className="flex flex-col items-center gap-3 py-14 text-sm text-ink-500 dark:text-stone-400">
          <span className="text-accent-600 dark:text-accent-400">
            <Spinner />
          </span>
          {runningLabel}
          <span className="tabular-nums text-xs">{elapsed.toFixed(0)} s</span>
        </div>
      )}
      {task.status === "error" && <Alert tone="error">{task.message}</Alert>}
      {task.status === "done" && render(task.data)}
    </div>
  );
}

function Header() {
  return (
    <header className="mx-auto max-w-7xl px-4 pb-8 pt-10 sm:px-6 lg:px-8">
      <div className="flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-lg bg-accent-600 text-white">
          <Icon name="scale" className="size-5" />
        </span>
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-ink-900 dark:text-stone-100">Legal Document Extractor</h1>
          <p className="text-sm text-ink-600 dark:text-stone-400">
            Structured data from Greek notarial deeds, powered by Gemini vision.
          </p>
        </div>
      </div>
    </header>
  );
}
