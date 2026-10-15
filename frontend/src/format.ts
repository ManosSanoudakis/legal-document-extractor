const euro = new Intl.NumberFormat("el-GR", { style: "currency", currency: "EUR" });
const decimal = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 2 });

export function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** 185000 → "185.000,00 €" */
export function price(value: unknown): string {
  return typeof value === "number" ? euro.format(value) : text(value);
}

/** 85.4 → "85,4 m²" */
export function area(value: unknown): string {
  return typeof value === "number" ? `${decimal.format(value)} m²` : text(value);
}

export function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
