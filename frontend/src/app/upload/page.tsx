"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ApiError, getUpload, uploadCalendar, uploadSales } from "@/lib/api";
import { generateDemoCsv } from "@/lib/demoData";
import type { UploadStatus } from "@/lib/types";

/**
 * idle → uploading → processing → done | failed | stalled
 *
 * "processing" is the window the old implementation could not express: the
 * server has accepted the file (202) but has not finished loading it.
 */
type Phase = "idle" | "uploading" | "processing" | "done" | "failed" | "stalled";

const POLL_MS = 2_000;
/** Stop polling rather than spinning forever if the row never goes terminal. */
const POLL_TIMEOUT_MS = 120_000;

function uploadErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 400) return e.problem.detail ?? "That file was rejected. Check the columns and try again.";
    if (e.status === 401) return "Your session expired. Sign in again to upload.";
    if (e.status === 413) return "That file is too large. The limit is 10 MB.";
    if (e.status === 429) return "Upload limit reached (10 per hour). Try again a little later.";
    if (e.status >= 500) return "The server had a problem accepting the file. Try again in a moment.";
    return e.problem.detail ?? e.message;
  }
  return "Couldn't reach the server. Check your connection and try again.";
}

function useUploadFlow() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [status, setStatus] = useState<UploadStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const clear = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  // Navigating away mid-upload must not leave the interval running.
  useEffect(() => clear, [clear]);

  const start = useCallback(
    async (file: File, kind: "sales" | "calendar") => {
      clear();
      setError(null);
      setStatus(null);
      setPhase("uploading");

      let acceptedId: string;
      try {
        const accepted = kind === "sales" ? await uploadSales(file) : await uploadCalendar(file);
        acceptedId = accepted.upload_id;
      } catch (e) {
        setPhase("failed");
        setError(uploadErrorMessage(e));
        return;
      }

      setPhase("processing");
      const startedAt = Date.now();
      timer.current = setInterval(async () => {
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          clear();
          setPhase("stalled");
          return;
        }
        try {
          const s = await getUpload(acceptedId);
          if (s.status === "loaded") {
            clear();
            setStatus(s);
            setPhase("done");
          } else if (s.status === "failed") {
            clear();
            setStatus(s);
            setPhase("failed");
          }
        } catch (e) {
          // Previously swallowed, which made a mid-flight failure look
          // identical to nothing happening.
          clear();
          setPhase("failed");
          setError(uploadErrorMessage(e));
        }
      }, POLL_MS);
    },
    [clear],
  );

  const busy = phase === "uploading" || phase === "processing";
  return { phase, status, error, busy, start };
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
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-[var(--c-rule)] bg-[var(--c-surface)] p-8 text-center transition-colors hover:border-[var(--c-brand)] focus-within:border-[var(--c-brand)] ${
        busy ? "pointer-events-none opacity-50" : ""
      }`}
    >
      <span className="text-sm font-medium text-[var(--c-ink)]">{label}</span>
      <span className="mt-1 text-xs text-[var(--c-muted)]">Click to choose a file</span>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        disabled={busy}
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
    </label>
  );
}

/** Visible progress between "accepted" and a terminal state. */
function ProgressNote({ phase }: { phase: Phase }) {
  if (phase === "uploading") {
    return (
      <p role="status" aria-live="polite" className="text-sm text-[var(--c-ink-soft)]">
        Uploading your file…
      </p>
    );
  }
  if (phase === "processing") {
    return (
      <p role="status" aria-live="polite" className="text-sm text-[var(--c-ink-soft)]">
        Validating and loading rows… this usually takes a few seconds.
      </p>
    );
  }
  if (phase === "stalled") {
    return (
      <p
        role="status"
        className="rounded-lg bg-[var(--c-stale-bg)] p-3 text-sm text-[var(--c-stale)]"
      >
        Still processing after two minutes. Your file was accepted — reload the Data
        page shortly to see the result.
      </p>
    );
  }
  return null;
}

function UploadResult({ status }: { status: UploadStatus }) {
  const rejected = status.error_report?.rejected_rows ?? [];
  const ok = status.status === "loaded";
  return (
    <div
      role="status"
      className={`rounded-lg p-3 text-sm ${
        ok
          ? "bg-[var(--c-live-bg)] text-[var(--c-live)]"
          : "bg-[var(--c-danger-bg)] text-[var(--c-danger)]"
      }`}
    >
      {ok ? (
        <>
          Loaded <span className="tabular">{status.row_count}</span> rows.
          {rejected.length > 0 && ` ${rejected.length} rows were rejected:`}
        </>
      ) : (
        <>Upload failed.{rejected.length > 0 && " Details:"}</>
      )}
      {rejected.length > 0 && (
        <ul className="mt-1 max-h-32 overflow-auto text-xs">
          {rejected.slice(0, 20).map((r, i) => (
            <li key={i}>
              Row <span className="tabular">{r.row}</span> — {r.field}: {r.message}
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

  return (
    <AppShell>
      <h1 className="mb-4 text-2xl font-bold text-[var(--c-ink)]">Your data</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-[var(--c-ink)]">Sales history (CSV)</h2>
          <p className="text-xs text-[var(--c-muted)]">
            Required columns:{" "}
            <code className="rounded bg-[var(--c-raised)] px-1">
              date, sku, product_name, quantity, revenue
            </code>{" "}
            — optional:{" "}
            <code className="rounded bg-[var(--c-raised)] px-1">price, promo_flag</code>
          </p>
          <Dropzone
            label="Upload sales CSV"
            accept=".csv,text/csv"
            busy={sales.busy}
            onFile={(f) => sales.start(f, "sales")}
          />
          <ProgressNote phase={sales.phase} />
          {sales.error && (
            <p role="alert" className="text-sm text-[var(--c-danger)]">
              {sales.error}
            </p>
          )}
          {sales.status && <UploadResult status={sales.status} />}
          <div className="rounded-lg bg-[var(--c-brand-bg)] p-3">
            <p className="text-sm text-[var(--c-ink)]">
              No data yet? Generate a realistic demo dataset — it flows through the exact
              same pipeline.
            </p>
            <button
              disabled={sales.busy}
              onClick={() => sales.start(generateDemoCsv(400), "sales")}
              className="mt-2 rounded-lg bg-[var(--c-brand)] px-3 py-1.5 text-sm font-medium text-[var(--c-on-brand)] transition-colors hover:bg-[var(--c-brand-hover)] disabled:opacity-50"
            >
              {sales.busy ? "Generating…" : "Generate demo data (5 SKUs, 400 days)"}
            </button>
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-[var(--c-ink)]">
            School vacations (optional)
          </h2>
          <p className="text-xs text-[var(--c-muted)]">
            ICS calendar export, or CSV with{" "}
            <code className="rounded bg-[var(--c-raised)] px-1">
              label, start_date, end_date
            </code>
            .
          </p>
          <Dropzone
            label="Upload calendar (ICS/CSV)"
            accept=".ics,.csv,text/calendar,text/csv"
            busy={calendar.busy}
            onFile={(f) => calendar.start(f, "calendar")}
          />
          <ProgressNote phase={calendar.phase} />
          {calendar.error && (
            <p role="alert" className="text-sm text-[var(--c-danger)]">
              {calendar.error}
            </p>
          )}
          {calendar.status && <UploadResult status={calendar.status} />}

          <div className="rounded-lg bg-[var(--c-raised)] p-3 text-xs text-[var(--c-muted)]">
            After your first upload, forecasts are computed by the nightly batch job and
            appear on the dashboard the next morning.
          </div>
        </section>
      </div>
    </AppShell>
  );
}
