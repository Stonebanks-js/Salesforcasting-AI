"use client";

import useSWR from "swr";
import { getSignalStatus } from "@/lib/api";

const STATUS_DOT: Record<string, string> = {
  live: "bg-green-500",
  stale: "bg-amber-400",
  degraded: "bg-orange-500",
  disabled: "bg-gray-300",
};

/** Per-feed health dots with tooltip; refreshes every 60s. */
export function SignalHealthStrip() {
  const { data } = useSWR("/signals/status", getSignalStatus, {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  });

  const items = data?.items ?? [];
  const live = items.filter((i) => i.status === "live").length;

  return (
    <div
      className="flex items-center gap-1.5"
      role="status"
      aria-label={`Signal health: ${live} of ${items.length} feeds live`}
    >
      {items.length > 0 && (
        <span className="mr-1 hidden text-xs text-gray-500 sm:inline">
          {live}/{items.length} live
        </span>
      )}
      {items.map((s) => (
        <span
          key={s.signal}
          title={`${s.signal}: ${s.status}${
            s.last_success_at
              ? ` (last ok ${new Date(s.last_success_at).toLocaleString()})`
              : ""
          }`}
          className={`h-2.5 w-2.5 rounded-full ${STATUS_DOT[s.status] ?? "bg-gray-300"}`}
        />
      ))}
      {items.length === 0 && (
        <span className="text-xs text-gray-400">signals unknown</span>
      )}
    </div>
  );
}
