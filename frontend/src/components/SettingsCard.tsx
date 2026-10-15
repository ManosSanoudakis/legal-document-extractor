import { useState } from "react";
import { Card, CardHeader, Segmented } from "./ui";

export function SettingsCard({
  apiKey,
  onApiKeyChange,
  models,
  model,
  onModelChange,
}: {
  apiKey: string;
  onApiKeyChange: (key: string) => void;
  models: string[];
  model: string;
  onModelChange: (model: string) => void;
}) {
  const [show, setShow] = useState(false);

  return (
    <Card>
      <CardHeader step="1" icon="key" title="Settings" subtitle="API access and model selection" />
      <div className="space-y-4 p-5">
        <div>
          <label htmlFor="api-key" className="text-sm font-medium text-ink-800 dark:text-stone-200">
            Gemini API key
          </label>
          <div className="mt-1.5 flex gap-2">
            <input
              id="api-key"
              type={show ? "text" : "password"}
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              placeholder="AIza…"
              autoComplete="off"
              spellCheck={false}
              className="min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 py-2 font-mono text-sm outline-none transition placeholder:text-ink-400 focus:border-accent-600 focus:ring-2 focus:ring-accent-600/20 dark:border-stone-700 dark:bg-stone-950"
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              className="rounded-lg border border-stone-300 px-3 text-xs font-medium text-ink-600 hover:bg-stone-50 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
            >
              {show ? "Hide" : "Show"}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-ink-500 dark:text-stone-400">
            Free key at{" "}
            <a
              href="https://aistudio.google.com/apikey"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-accent-700 hover:underline dark:text-accent-400"
            >
              aistudio.google.com
            </a>
            . Kept in this tab's memory only and never stored.
          </p>
        </div>

        <div>
          <span className="text-sm font-medium text-ink-800 dark:text-stone-200">Extraction model</span>
          <div className="mt-1.5">
            <Segmented
              label="Extraction model"
              value={model}
              onChange={onModelChange}
              options={models.map((m) => ({ value: m, label: m.replace("gemini-", "") }))}
            />
          </div>
          <p className="mt-1.5 text-xs text-ink-500 dark:text-stone-400">
            Flash is faster and cheaper. Pro is more accurate.
          </p>
        </div>
      </div>
    </Card>
  );
}
