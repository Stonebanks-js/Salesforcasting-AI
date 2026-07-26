"use client";

import { useCallback, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  getUpload,
  uploadCalendar,
  uploadSales,
} from "@/lib/api";
import { generateDemoCsv } from "@/lib/demoData";
import type { UploadStatus } from "@/lib/types";

function useUploadFlow() {
  const [status, setStatus] = useState<UploadStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = useCallback(async (file: File, kind: "sales" | "calendar") => {
    setError(null);
    setStatus(null);
    try {
      const accepted = kind === "sales" ? await uploadSales(file) : await uploadCalendar(file);
      // Poll until terminal state (contract: 202 + status_url pattern).
      await new Promise<void>((resolve) => {
        timer.current = setInterval(async () => {
          try {
            const s = await getUpload(accepted.upload_id);
            if (s.status === "loaded" || s.status === "failed") {
              clearInterval(timer.current!);
              setStatus(s);
              resolve();
            }
          } catch {
            clearInterval(timer.current!);
            resolve();
          }
        }, 2000);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  }, []);

  return { status, error, start };
}

function Dropzone({
  label,
  accept,
  onFile,
  busy,
}: {
  label: string;
  accept: string;
  onFile: (f: File) => void;
  busy: boolean;
}) {
  return (
    <label
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 bg-white p-8 text-center hover:border-[var(--c-series-1)] ${
        busy ? "pointer-events-none opacity-50" : ""
      }`}
    >
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <span className="mt-1 text-xs text-gray-400">Click to choose a file</span>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
    </label>
  );
}

function UploadResult({ status }: { status: UploadStatus }) {
  const rejected = status.error_report?.rejected_rows ?? [];
  return (
    <div
      role="status"
      className={`rounded-lg p-3 text-sm ${
        status.status === "loaded"
          ? "bg-green-50 text-green-800"
          : "bg-red-50 text-red-800"
      }`}
    >
      {status.status === "loaded" ? (
        <>
          ✅ Loaded {status.row_count} rows.
          {rejected.length > 0 && ` ${rejected.length} rows rejected:`}
        </>
      ) : (
        <>Upload failed.{rejected.length > 0 && " Details:"}</>
      )}
      {rejected.length > 0 && (
        <ul className="mt-1 max-h-32 overflow-auto text-xs">
          {rejected.slice(0, 20).map((r, i) => (
            <li key={i}>
              Row {r.row} — {r.field}: {r.message}
            </li>
          ))}
          {rejected.length > 20 && <li>…and {rejected.length - 20} more</li>}
        </ul>
      )}
    </div>
  );
}

export default function UploadPage() {
  const sales = useUploadFlow();
  const calendar = useUploadFlow();
  const [demoBusy, setDemoBusy] = useState(false);

  return (
    <AppShell>
      <h1 className="mb-4 text-2xl font-bold">Your data</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Sales history (CSV)</h2>
          <p className="text-xs text-gray-500">
            Required columns:{" "}
            <code className="rounded bg-gray-100 px-1">
              date, sku, product_name, quantity, revenue
            </code>{" "}
            — optional: <code className="rounded bg-gray-100 px-1">price, promo_flag</code>
          </p>
          <Dropzone
            label="Upload sales CSV"
            accept=".csv,text/csv"
            busy={sales.status?.status === "pending"}
            onFile={(f) => sales.start(f, "sales")}
          />
          {sales.error && <p role="alert" className="text-sm text-red-600">{sales.error}</p>}
          {sales.status && <UploadResult status={sales.status} />}
          <div className="rounded-lg bg-blue-50 p-3">
            <p className="text-sm text-blue-900">
              No data yet? Generate a realistic demo dataset — it flows through the exact
              same pipeline.
            </p>
            <button
              disabled={demoBusy}
              onClick={async () => {
                setDemoBusy(true);
                await sales.start(generateDemoCsv(400), "sales");
                setDemoBusy(false);
              }}
              className="mt-2 rounded-lg bg-[var(--c-series-1)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {demoBusy ? "Generating…" : "Generate demo data (5 SKUs, 400 days)"}
            </button>
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-lg font-semibold">School vacations (optional)</h2>
          <p className="text-xs text-gray-500">
            ICS calendar export, or CSV with{" "}
            <code className="rounded bg-gray-100 px-1">label, start_date, end_date</code>.
          </p>
          <Dropzone
            label="Upload calendar (ICS/CSV)"
            accept=".ics,.csv,text/calendar,text/csv"
            busy={false}
            onFile={(f) => calendar.start(f, "calendar")}
          />
          {calendar.error && (
            <p role="alert" className="text-sm text-red-600">{calendar.error}</p>
          )}
          {calendar.status && <UploadResult status={calendar.status} />}

          <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-500">
            After your first upload, forecasts are computed by the nightly batch job and
            appear on the dashboard the next morning.
          </div>
        </section>
      </div>
    </AppShell>
  );
}
