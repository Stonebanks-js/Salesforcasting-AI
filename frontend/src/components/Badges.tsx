export function MapeBadge({ mape }: { mape: number | null }) {
  if (mape == null) return null;
  const tone =
    mape <= 15
      ? "bg-green-100 text-green-800"
      : mape <= 25
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs font-medium ${tone}`}
      title="Backtest mean absolute percentage error (lower is better)"
    >
      MAPE {mape.toFixed(1)}%
    </span>
  );
}

export function ModelBadge({ version }: { version: string }) {
  const isBaseline = version.startsWith("seasonal-naive");
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs font-medium ${
        isBaseline ? "bg-gray-100 text-gray-700" : "bg-blue-100 text-blue-800"
      }`}
    >
      {version}
    </span>
  );
}

export function DegradedBadge({ reason }: { reason?: string }) {
  return (
    <span
      className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800"
      title={
        reason ??
        "Forecast is using fallback data because one or more external signals are stale or disabled. Predictions remain valid but may be less accurate."
      }
    >
      ⚠ degraded
    </span>
  );
}
