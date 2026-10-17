// Saved results, in one of two places (the server's /api/config says which):
// - "server": one shared history on the server, which saves each extraction itself
// - "browser": this visitor's own history, kept in this browser only; the server stores nothing
import { createContext, useContext } from "react";
import { deleteHistory, getHistory, listHistory, saveHistory } from "./api";
import type { Deed, ExtractionResult, HistoryItem, HistoryRecord } from "./types";

export interface HistoryStore {
  kind: "server" | "browser";
  list(): Promise<HistoryItem[]>;
  get(id: string): Promise<HistoryRecord>;
  /** Save a new extraction; returns its id, or null if it could not be saved. */
  add(filename: string, result: ExtractionResult): Promise<string | null>;
  /** Save corrections (null = none, the model's answer stands) and the fields ticked as checked. */
  update(id: string, edited: Deed | null, reviewed: string[]): Promise<void>;
  remove(id: string): Promise<void>;
}

export const serverHistory: HistoryStore = {
  kind: "server",
  list: listHistory,
  get: getHistory,
  // The server saves every extraction as it finishes and puts the id in the result
  add: async (_filename, result) => result.meta.history_id ?? null,
  update: async (id, edited, reviewed) => {
    await saveHistory(id, edited, reviewed);
  },
  remove: deleteHistory,
};

// ---------------------------------------------------------------------------
// In the browser
// ---------------------------------------------------------------------------

const KEY = "deed-extractor.history.v1";
const MAX_ENTRIES = 100; // the oldest go first when the limit or the browser's storage quota is reached

/** Values the history table shows: the same summary the server computes (see history.py). */
export function summarise(result: ExtractionResult, edited: Deed | null, reviewed: string[]): HistoryItem["summary"] {
  const txn = (edited ?? result.deed).transaction ?? {};
  const flagged = new Set(result.validation.map((i) => i.field));
  return {
    deed_type: txn.deed_type ?? null,
    price: typeof txn.price === "number" ? txn.price : null,
    date: txn.date ?? null,
    flags: result.validation.length,
    errors: result.validation.filter((i) => i.severity === "error").length,
    to_check: [...flagged].filter((f) => !reviewed.includes(f)).length,
  };
}

/** Browser storage can be missing or refuse to work (private windows, blocked site data). */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export function browserHistory(storage: KeyValueStore | null = safeLocalStorage()): HistoryStore & { available: boolean } {
  function read(): HistoryRecord[] {
    try {
      const records = JSON.parse(storage?.getItem(KEY) ?? "[]");
      return Array.isArray(records) ? records : [];
    } catch {
      return [];
    }
  }

  /** Write, dropping the oldest entries if the browser runs out of room. False if nothing could be saved. */
  function write(records: HistoryRecord[]): boolean {
    if (!storage) return false;
    let kept = records.toSorted((a, b) => b.created - a.created).slice(0, MAX_ENTRIES);
    for (;;) {
      try {
        storage.setItem(KEY, JSON.stringify(kept));
        return true;
      } catch {
        if (kept.length <= 1) return false;
        kept = kept.slice(0, Math.floor(kept.length / 2));
      }
    }
  }

  function find(id: string): HistoryRecord {
    const record = read().find((r) => r.id === id);
    if (!record) throw new Error("This result is no longer saved in this browser.");
    return record;
  }

  return {
    kind: "browser",
    available: storage !== null,
    list: async () =>
      read()
        .toSorted((a, b) => b.created - a.created)
        .map((r) => ({
          id: r.id,
          filename: r.filename,
          model: r.model,
          created: r.created,
          updated: r.updated,
          edited: r.edited !== null,
          summary: summarise(r.result, r.edited, r.reviewed),
        })),
    get: async (id) => find(id),
    add: async (filename, result) => {
      const now = Date.now() / 1000;
      const id = crypto.randomUUID();
      const saved = { ...result, meta: { ...result.meta, history_id: id } };
      const record: HistoryRecord = {
        id, filename, model: result.meta.model, created: now, updated: now, result: saved, edited: null, reviewed: [],
      };
      return write([record, ...read()]) && read().some((r) => r.id === id) ? id : null;
    },
    update: async (id, edited, reviewed) => {
      const records = read();
      const record = records.find((r) => r.id === id);
      if (!record) throw new Error("This result is no longer saved in this browser.");
      Object.assign(record, { edited, reviewed, updated: Date.now() / 1000 });
      if (!write(records)) throw new Error("This browser has no room left to save it.");
    },
    remove: async (id) => {
      write(read().filter((r) => r.id !== id));
    },
  };
}

function safeLocalStorage(): KeyValueStore | null {
  try {
    const storage = window.localStorage;
    storage.getItem(KEY); // throws where site data is blocked
    return storage;
  } catch {
    return null;
  }
}

/** Remove every result saved in this browser. */
export function clearBrowserHistory(storage: KeyValueStore | null = safeLocalStorage()): void {
  try {
    storage?.setItem(KEY, "[]");
  } catch {
    // nothing saved, nothing to clear
  }
}

/** Save a new result to history (in server mode the server already has) and give it its history id. */
export async function remember(store: HistoryStore, filename: string, result: ExtractionResult): Promise<ExtractionResult> {
  const id = await store.add(filename, result);
  return id ? { ...result, meta: { ...result.meta, history_id: id } } : result;
}

// ---------------------------------------------------------------------------

export const HistoryContext = createContext<HistoryStore>(serverHistory);

export function useHistoryStore(): HistoryStore {
  return useContext(HistoryContext);
}
