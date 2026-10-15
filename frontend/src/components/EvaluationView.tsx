import { text } from "../format";
import type { Completeness, EvaluationReport, ModelRun } from "../types";
import { JsonPanel } from "./ResultsView";
import { Alert, Badge, Cell, SectionTitle, Stat, Table } from "./ui";

function completeness(run: ModelRun): Partial<Completeness> {
  return run.completeness as Partial<Completeness>;
}

function Bar({ pct }: { pct: number | undefined }) {
  if (pct === undefined) return <Cell value={null} />;
  return (
    <div className="flex min-w-28 items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800">
        <div className="h-full rounded-full bg-gradient-to-r from-accent-500 to-accent-700 dark:from-accent-400 dark:to-accent-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-12 text-right tabular-nums">{pct}%</span>
    </div>
  );
}

export function EvaluationView({ report }: { report: EvaluationReport }) {
  const runs = report.models;
  const byName = Object.fromEntries(runs.map((r) => [r.model, r]));
  const winner = report.winner;
  const [a, b] = runs;

  return (
    <div className="space-y-6">
      {winner && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Stat
            label="Most complete"
            icon="award"
            tone="emerald"
            value={winner.accuracy}
            sub={`${completeness(byName[winner.accuracy]).overall_pct}% of fields filled`}
          />
          <Stat label="Fastest" icon="bolt" tone="amber" value={winner.speed} sub={`${byName[winner.speed].elapsed_s.toFixed(1)} s`} />
        </div>
      )}

      <div>
        <SectionTitle>Model comparison</SectionTitle>
        <Table
          rows={runs}
          empty="No results."
          columns={[
            { header: "Model", cell: (r) => r.model, className: "font-medium whitespace-nowrap" },
            { header: "Overall", cell: (r) => <Bar pct={completeness(r).overall_pct} /> },
            { header: "Single fields", cell: (r) => <Bar pct={completeness(r).scalar_pct} /> },
            { header: "Party fields", cell: (r) => <Bar pct={completeness(r).list_pct} /> },
            { header: "Time", cell: (r) => `${r.elapsed_s.toFixed(2)} s`, className: "tabular-nums whitespace-nowrap" },
            {
              header: "Status",
              cell: (r) => (r.error ? <Badge tone="error">{r.error}</Badge> : <Badge tone="success">OK</Badge>),
            },
          ]}
        />
        <p className="mt-2 text-xs text-ink-500 dark:text-stone-400">
          Completeness is the share of schema fields a model filled in. It is a proxy for accuracy, since there
          is no ground truth to compare against.
        </p>
      </div>

      <div>
        <SectionTitle>Fields where the models disagree</SectionTitle>
        {!report.field_diffs ? (
          <Alert tone="info">Not available because at least one model run failed.</Alert>
        ) : report.field_diffs.length === 0 ? (
          <Alert tone="info">Both models agree on every field they both filled in.</Alert>
        ) : (
          <Table
            rows={report.field_diffs}
            empty=""
            columns={[
              { header: "Field", cell: (d) => d.field, className: "font-mono text-xs whitespace-nowrap" },
              { header: a?.model ?? "Model A", cell: (d) => text(d.model_a) },
              { header: b?.model ?? "Model B", cell: (d) => text(d.model_b) },
            ]}
          />
        )}
      </div>

      <details className="group rounded-xl border border-stone-200 dark:border-stone-800">
        <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium">Full report (JSON)</summary>
        <div className="border-t border-stone-200 p-4 dark:border-stone-800">
          <JsonPanel data={report} filename="evaluation_results.json" />
        </div>
      </details>
    </div>
  );
}
