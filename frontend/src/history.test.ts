import { describe, expect, it } from "vitest";
import { browserHistory, clearBrowserHistory, type KeyValueStore } from "./history";
import type { ExtractionResult } from "./types";

function memory(): KeyValueStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) };
}

function result(price: number): ExtractionResult {
  return {
    deed: { transaction: { deed_type: "sale", price, date: "2024-01-01" } },
    meta: { model: "gemini-test", provider: "gemini", pages: 1, text_layer: true, elapsed_seconds: 1 },
    validation: [
      { field: "property.kaek", value: "1", message: "a", severity: "error" },
      { field: "property.kaek", value: "1", message: "b", severity: "warning" },
      { field: "sellers[0].tax_id", value: "2", message: "c", severity: "warning" },
    ],
  };
}

describe("browser history", () => {
  it("saves, lists newest first and reopens a result with its id", async () => {
    const store = browserHistory(memory());
    const first = await store.add("a.pdf", result(1));
    const second = await store.add("b.pdf", result(2));
    expect(first).toBeTruthy();
    const items = await store.list();
    expect(items.map((i) => i.filename)).toEqual(["b.pdf", "a.pdf"]);
    expect(items[0].summary).toEqual({ deed_type: "sale", price: 2, date: "2024-01-01", flags: 3, errors: 1, to_check: 2 });
    const record = await store.get(second!);
    expect(record.result.meta.history_id).toBe(second); // so edits made after reopening are saved too
  });

  it("keeps corrections and checked fields", async () => {
    const store = browserHistory(memory());
    const id = (await store.add("a.pdf", result(1)))!;
    await store.update(id, { transaction: { deed_type: "sale", price: 999, date: "2024-01-01" } }, ["property.kaek"]);
    const [item] = await store.list();
    expect(item.edited).toBe(true);
    expect(item.summary.price).toBe(999); // the table shows the corrected value
    expect(item.summary.to_check).toBe(1);
    await store.remove(id);
    expect(await store.list()).toEqual([]);
    await expect(store.get(id)).rejects.toThrow("no longer saved");
  });

  it("drops the oldest entries when the browser runs out of room", async () => {
    const storage = memory();
    const store = browserHistory({
      getItem: storage.getItem,
      setItem: (k, v) => {
        if (v.length > 2500) throw new Error("QuotaExceededError");
        storage.setItem(k, v);
      },
    });
    for (let i = 1; i <= 6; i++) await store.add(`${i}.pdf`, result(i));
    const names = (await store.list()).map((i) => i.filename);
    expect(names[0]).toBe("6.pdf"); // the newest is always kept
    expect(names.length).toBeLessThan(6);
  });

  it("works, saving nothing, where the browser blocks storage", async () => {
    const store = browserHistory(null);
    expect(store.available).toBe(false);
    expect(await store.add("a.pdf", result(1))).toBeNull();
    expect(await store.list()).toEqual([]);
  });

  it("can be cleared", async () => {
    const storage = memory();
    const store = browserHistory(storage);
    await store.add("a.pdf", result(1));
    clearBrowserHistory(storage);
    expect(await store.list()).toEqual([]);
  });
});
