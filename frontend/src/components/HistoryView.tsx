import { useEffect, useState } from "react";
import { deleteHistory, exportBatch, getHistory, listHistory } from "../api";
import { deedData } from "../deed";
import { deedType, price } from "../format";
import type { HistoryItem, HistoryRecord } from "../types";
import { ResultsView } from "./ResultsView";
import { Alert, Badge, Button, Cell, Icon, Spinner, Table } from "./ui";

const day = new Intl.DateTimeFormat("el-GR", { dateStyle: "short" });
const when = new Intl.DateTimeFormat("el-GR", { dateStyle: "short", timeStyle: "short" });

/** Earlier results: extracted values and corrections only, never the PDFs. */
export function HistoryView() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<HistoryRecord | null>(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    listHistory()
      .then(setItems)
      .catch((err: Error) => setError(err.message));
  }

  useEffect(refresh, []);

  async function show(item: HistoryItem) {
    if (open?.id === item.id) {
      setOpen(null);
      refresh(); // the list shows corrected values and what is left to check
      return;
    }
    try {
      setOpen(await getHistory(item.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open this result");
    }
  }

  async function remove(item: HistoryItem) {
    if (!window.confirm(`Delete the saved result for ${item.filename}? This cannot be undone.`)) return;
    try {
      await deleteHistory(item.id);
      if (open?.id === item.id) setOpen(null);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function download(format: "xlsx" | "csv") {
    if (!items) return;
    setBusy(true);
    setError(null);
    try {
      const records = await Promise.all(items.map((i) => getHistory(i.id)));
      await exportBatch(
        records.map((r) => ({ name: r.filename, deed: deedData(r.edited ?? r.result) })),
        format,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setBusy(false);
    }
  }

  if (!items && !error) {
    return (
      <p className="flex items-center gap-2 text-sm text-ink-500">
        <Spinner /> Loading history…
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-600 dark:text-stone-400">
          Every extraction is saved here with your corrections. Only the extracted values are kept, never the PDF:
          upload it again to see its pages or take a second look.
        </p>
        {items && items.length > 0 && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => download("xlsx")} disabled={busy}>
              {busy ? <Spinner /> : <Icon name="download" />} Excel (all)
            </Button>
            <Button variant="secondary" onClick={() => download("csv")} disabled={busy}>
              <Icon name="download" /> CSV (all)
            </Button>
          </div>
        )}
      </div>
      {error && <Alert tone="error">{error}</Alert>}

      {items && (
        <Table
          rows={items}
          empty="Nothing yet. Results appear here after an extraction."
          columns={[
            {
              header: "File",
              cell: (i) => (
                <>
                  <span className="font-medium">{i.filename}</span>
                  {i.edited && <span className="block text-xs text-ink-500">edited</span>}
                </>
              ),
            },
            {
              header: "Saved",
              cell: (i) => <span title={when.format(new Date(i.created * 1000))}>{day.format(new Date(i.created * 1000))}</span>,
              className: "whitespace-nowrap",
            },
            { header: "Deed type", cell: (i) => <Cell value={deedType(i.summary.deed_type)} /> },
            { header: "Price", cell: (i) => <Cell value={price(i.summary.price)} />, className: "whitespace-nowrap" },
            {
              header: "To check",
              cell: (i) =>
                i.summary.to_check ? (
                  <span className="text-amber-700 dark:text-amber-300">{i.summary.to_check}</span>
                ) : (
                  <Badge tone="success">Done</Badge>
                ),
            },
            {
              header: "",
              className: "whitespace-nowrap text-right",
              cell: (i) => (
                <span className="inline-flex gap-3">
                  <button type="button" className="text-sm font-medium text-accent-700 hover:underline dark:text-accent-300" onClick={() => show(i)}>
                    {open?.id === i.id ? "Close" : "Open"}
                  </button>
                  <button type="button" aria-label={`Delete ${i.filename}`} className="text-ink-500 hover:text-red-600" onClick={() => remove(i)}>
                    <Icon name="x" />
                  </button>
                </span>
              ),
            },
          ]}
        />
      )}

      {open && (
        <div className="rounded-xl border border-stone-200 p-4 dark:border-stone-800">
          <p className="mb-4 font-semibold">{open.filename}</p>
          <ResultsView
            key={open.id}
            result={{ ...open.result, _meta: { ...open.result._meta!, history_id: open.id } }}
            saved={{ edited: open.edited, reviewed: open.reviewed }}
          />
        </div>
      )}
    </div>
  );
}
