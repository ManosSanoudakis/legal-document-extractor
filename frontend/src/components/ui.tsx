import type { ButtonHTMLAttributes, ReactNode } from "react";
import { text } from "../format";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------------ */
/* Icons (inline SVG, stroke follows currentColor)                           */
/* ------------------------------------------------------------------------ */

const iconPaths = {
  scale: "M12 3v18M5 21h14M7 7h10M7 7l-3 7a3 3 0 0 0 6 0L7 7Zm10 0-3 7a3 3 0 0 0 6 0l-3-7ZM12 3l-5 4m5-4 5 4",
  key: "M15.5 7.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0ZM12 11v10m0-4h3m-3 3h2",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Zm0 0v5h5M9 13h6m-6 4h6",
  upload: "M12 16V4m0 0-4 4m4-4 4 4M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3",
  play: "M7 5v14l11-7L7 5Z",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  doc: "M8 7h8M8 11h8M8 15h5M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z",
  check: "M5 12.5 10 17l9-10",
  x: "M6 6l12 12M18 6 6 18",
  award: "M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12Zm-3.5 4.5L9 14m6.5 5.5L15 14m-6.5 5.5L12 18l3.5 1.5",
  bolt: "M13 2 4 14h7l-1 8 9-12h-7l1-8Z",
  copy: "M9 9h10v10H9V9Zm-4 6V5h10",
  download: "M12 4v12m0 0-4-4m4 4 4-4M4 20h16",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  info: "M12 8h.01M11 12h1v5h1M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z",
  alert: "M12 9v4m0 4h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
} as const;

export type IconName = keyof typeof iconPaths;

export function Icon({ name, className = "size-4" }: { name: IconName; className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cx("shrink-0", className)}
    >
      <path d={iconPaths[name]} />
    </svg>
  );
}

/* ------------------------------------------------------------------------ */
/* Layout                                                                    */
/* ------------------------------------------------------------------------ */

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={cx(
        "overflow-hidden rounded-xl border border-[#d8c7ae] bg-[#fbf8f2] shadow-sm shadow-[#6b5a3e]/5 dark:border-stone-800 dark:bg-stone-900",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  step,
  icon,
  title,
  aside,
}: {
  step?: string;
  icon?: IconName;
  title: string;
  subtitle?: string;
  aside?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-5 pb-1 pt-5">
      <div className="flex items-center gap-3">
        {icon && <Icon name={icon} className="size-4 text-accent-600 dark:text-accent-400" />}
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink-900 dark:text-white">
            {step && (
              <span className="text-xs font-medium tabular-nums text-accent-600 dark:text-accent-400">{step.padStart(2, "0")}</span>
            )}
            {title}
          </h2>
        </div>
      </div>
      {aside}
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* Controls                                                                  */
/* ------------------------------------------------------------------------ */

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" }) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary"
          ? "bg-accent-600 text-white hover:bg-accent-700 disabled:hover:bg-accent-600"
          : "border border-stone-200 bg-white text-ink-700 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200 dark:hover:bg-stone-700",
        className,
      )}
      {...props}
    />
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex rounded-lg bg-stone-200/80 p-1 dark:bg-stone-800"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition",
            value === o.value
              ? "bg-white text-accent-600 shadow-sm dark:bg-stone-700 dark:text-white"
              : "text-ink-500 hover:text-ink-800 dark:text-stone-400 dark:hover:text-stone-200",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: T; label: string; icon?: IconName }[];
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-stone-200 dark:border-stone-800">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={active === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "-mb-px inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-sm font-medium transition",
            active === t.id
              ? "border-accent-600 text-accent-600 dark:border-accent-400 dark:text-accent-400"
              : "border-transparent text-ink-500 hover:text-ink-800 dark:text-stone-400 dark:hover:text-stone-200",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* Data display                                                              */
/* ------------------------------------------------------------------------ */

const EMPTY = "Not found";

/** Label/value pairs in a responsive grid. Empty values show a muted placeholder. */
export function FieldGrid({ fields }: { fields: [label: string, value: unknown][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
      {fields.map(([label, value]) => {
        const v = text(value);
        return (
          <div key={label} className="min-w-0">
            <dt className="text-xs text-ink-500 dark:text-stone-400">
              {label}
            </dt>
            <dd
              className={cx(
                "mt-1 break-words text-sm font-medium text-ink-900 dark:text-stone-100",
                !v && "font-normal italic text-ink-400 dark:text-stone-500",
              )}
            >
              {v || EMPTY}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

type Tone = "blue" | "emerald" | "violet" | "amber";

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: IconName;
  tone?: Tone;
}) {
  return (
    <div className="min-w-0 border-l-2 border-accent-600 pl-3 dark:border-accent-400">
      <div className="min-w-0">
        <div className="text-xs text-ink-500 dark:text-stone-400">
          {label}
        </div>
        <div
          className={cx(
            "mt-0.5 truncate text-base font-semibold text-ink-900 dark:text-white",
            !value && "font-normal italic text-ink-400 dark:text-stone-500",
          )}
          title={value}
        >
          {value || EMPTY}
        </div>
        {sub && <div className="mt-0.5 truncate text-xs text-ink-500 dark:text-stone-400">{sub}</div>}
      </div>
    </div>
  );
}

export function Badge({ tone, children }: { tone: "success" | "error"; children: ReactNode }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset",
        tone === "success"
          ? "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-900"
          : "bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/50 dark:text-red-300 dark:ring-red-900",
      )}
    >
      <Icon name={tone === "success" ? "check" : "x"} className="size-3" />
      {children}
    </span>
  );
}

export function Table<Row>({
  columns,
  rows,
  empty,
}: {
  columns: { header: string; cell: (row: Row) => ReactNode; className?: string }[];
  rows: Row[];
  empty: string;
}) {
  if (rows.length === 0) return <p className="text-sm italic text-ink-500 dark:text-stone-400">{empty}</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-stone-200 dark:border-stone-800">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-stone-200 text-xs text-ink-500 dark:border-stone-800 dark:text-stone-400">
          <tr>
            {columns.map((c) => (
              <th key={c.header} scope="col" className="whitespace-nowrap px-4 py-2.5 font-medium">
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.header} className={cx("px-4 py-3 align-top", c.className)}>
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Table cell value with a muted placeholder for missing data. */
export function Cell({ value }: { value: unknown }) {
  const v = text(value);
  return v ? <>{v}</> : <span className="font-normal italic text-ink-400 dark:text-stone-500">{EMPTY}</span>;
}

export function Alert({ tone, children }: { tone: "error" | "warning" | "info"; children: ReactNode }) {
  const styles = {
    error: "border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300",
    warning: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200",
    info: "border-stone-300/60 bg-stone-200/50 text-ink-600 dark:border-stone-800 dark:bg-stone-800/40 dark:text-stone-300",
  }[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cx("flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm", styles)}
    >
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent"
    />
  );
}

export function SectionTitle({ children, count }: { children: ReactNode; count?: number }) {
  return (
    <h3 className="mb-2.5 flex items-center gap-2 text-sm font-semibold text-ink-800 dark:text-stone-200">
      {children}
      {count !== undefined && (
        <span className="text-xs font-normal text-ink-400">
          {count}
        </span>
      )}
    </h3>
  );
}
