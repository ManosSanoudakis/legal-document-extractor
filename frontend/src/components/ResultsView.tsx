import { useState } from "react";
import { area, deedType, downloadJson, fieldLabel, price, text } from "../format";
import type { ExtractionResult, Party, Representative, ValidationIssue } from "../types";
import { Alert, Button, Cell, FieldGrid, Icon, SectionTitle, Stat, Table, Tabs } from "./ui";

type Tab = "parties" | "property" | "notary" | "json";

const partyColumns = [
  { header: "Name", cell: (p: Party) => <Cell value={p.full_name} />, className: "font-medium" },
  { header: "Tax ID (ΑΦΜ)", cell: (p: Party) => <Cell value={p.tax_id} />, className: "font-mono text-xs" },
  { header: "ID document", cell: (p: Party) => <Cell value={p.id_document} />, className: "whitespace-nowrap" },
  { header: "Address", cell: (p: Party) => <Cell value={p.address} /> },
];

const repColumns = [
  { header: "Name", cell: (r: Representative) => <Cell value={r.full_name} />, className: "font-medium" },
  { header: "Represents", cell: (r: Representative) => <Cell value={r.represents} /> },
  { header: "Tax ID (ΑΦΜ)", cell: (r: Representative) => <Cell value={r.tax_id} />, className: "font-mono text-xs" },
  { header: "ID document", cell: (r: Representative) => <Cell value={r.id_document} />, className: "whitespace-nowrap" },
];

export function ResultsView({ result }: { result: ExtractionResult }) {
  const [tab, setTab] = useState<Tab>("parties");
  const notary = result.notary ?? {};
  const prop = result.property ?? {};
  const txn = result.transaction ?? {};
  const sellers = result.sellers ?? [];
  const buyers = result.buyers ?? [];
  const reps = (result.legal_representatives ?? []).filter((r) => r.full_name);
  const meta = result._meta;

  return (
    <div className="space-y-5">
      {result._error && (
        <Alert tone="warning">
          The model's response was not valid JSON, so the fields are empty. Details: {result._error}
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Deed type" value={deedType(txn.deed_type)} icon="doc" tone="blue" />
        <Stat label="Price" value={price(txn.price)} icon="chart" tone="emerald" />
        <Stat label="Date" value={text(txn.date)} icon="file" tone="violet" />
        <Stat label="Area" value={area(prop.area_sqm)} icon="scale" tone="amber" />
      </div>
      <Checks issues={result._validation} />
      {meta && (
        <p className="text-xs text-ink-500 dark:text-stone-400">
          {meta.model} · {meta.pages} page{meta.pages === 1 ? "" : "s"} · {meta.elapsed_seconds} s
        </p>
      )}

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "parties", label: `Parties (${sellers.length + buyers.length})` },
          { id: "property", label: "Property" },
          { id: "notary", label: "Notary" },
          { id: "json", label: "JSON" },
        ]}
      />

      {tab === "parties" && (
        <div className="space-y-5">
          <div>
            <SectionTitle count={sellers.length}>Sellers</SectionTitle>
            <Table columns={partyColumns} rows={sellers} empty="No sellers found." />
          </div>
          <div>
            <SectionTitle count={buyers.length}>Buyers</SectionTitle>
            <Table columns={partyColumns} rows={buyers} empty="No buyers found." />
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
              ["Type", prop.type],
              ["Floor", prop.floor],
              ["Area", area(prop.area_sqm)],
              ["Municipal unit", prop.municipal_unit],
              ["Address", prop.address],
            ]}
          />
          <div className="border-t border-stone-100 pt-5 dark:border-stone-800">
            <SectionTitle>Land registry</SectionTitle>
            <FieldGrid
              fields={[
                ["KAEK", prop.kaek],
                ["Building permit", prop.building_permit],
              ]}
            />
          </div>
        </div>
      )}

      {tab === "notary" && (
        <FieldGrid
          fields={[
            ["Notary", notary.name],
            ["Location", notary.location],
            ["Registry number", notary.registry_number],
          ]}
        />
      )}

      {tab === "json" && <JsonPanel data={result} filename="extracted_legal_data.json" />}
    </div>
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
function Checks({ issues }: { issues: ValidationIssue[] | undefined }) {
  if (!issues) return null;
  if (issues.length === 0) {
    return <Alert tone="info">All automatic checks passed: tax IDs, ΚΑΕΚ format, date and amounts.</Alert>;
  }
  const hasErrors = issues.some((i) => i.severity === "error");
  return (
    <Alert tone={hasErrors ? "error" : "warning"}>
      <p className="font-semibold">
        {issues.length} {issues.length === 1 ? "value needs" : "values need"} checking against the document
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
