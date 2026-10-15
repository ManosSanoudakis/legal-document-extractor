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

const DEED_TYPES: Record<string, string> = {
  sale: "Sale",
  parental_provision: "Parental provision",
  donation: "Donation",
  other: "Other",
};

/** "parental_provision" → "Parental provision" */
export function deedType(value: unknown): string {
  const v = text(value);
  return DEED_TYPES[v] ?? v;
}

/** "sellers[0].tax_id" → "Seller 1 · tax ID" */
export function fieldLabel(field: string): string {
  const names: Record<string, string> = {
    sellers: "Seller", buyers: "Buyer", legal_representatives: "Representative",
    tax_id: "tax ID (ΑΦΜ)", id_document: "ID document", full_name: "name", area_sqm: "area",
    kaek: "ΚΑΕΚ", deed_type: "deed type", registry_number: "registry number",
    building_permit: "building permit", municipal_unit: "municipal unit",
  };
  const m = field.match(/^(\w+)\[(\d+)\]\.(\w+)$/);
  if (m) return `${names[m[1]] ?? m[1]} ${Number(m[2]) + 1} · ${names[m[3]] ?? m[3]}`;
  const [section, key] = field.split(".");
  if (!key) return names[section] ? `${names[section]}s` : section;
  const label = names[key] ?? key.replace(/_/g, " ");
  return `${section[0].toUpperCase()}${section.slice(1)} · ${label}`;
}
