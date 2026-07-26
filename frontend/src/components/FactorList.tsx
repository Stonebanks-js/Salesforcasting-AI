import type { Factor } from "@/lib/types";

const ARROW = { up: "▲", down: "▼", neutral: "●" } as const;
const TONE = { up: "text-green-600", down: "text-red-500", neutral: "text-gray-400" } as const;

/** Top-5 external factors driving a forecast, with direction and weight. */
export function FactorList({ factors }: { factors: Factor[] }) {
  if (factors.length === 0) {
    return <p className="text-xs text-gray-400">No external factor data for this run.</p>;
  }
  return (
    <ul className="space-y-1" aria-label="Top factors influencing this forecast">
      {factors.map((f) => {
        const dir = f.direction ?? "neutral";
        return (
          <li key={f.factor} className="flex items-center gap-2 text-xs">
            <span className={TONE[dir]} aria-hidden="true">
              {ARROW[dir]}
            </span>
            <span className="w-36 truncate text-gray-700" title={f.factor}>
              {f.factor.replace(/_/g, " ")}
            </span>
            <span className="h-1.5 flex-1 rounded bg-gray-100">
              <span
                className="block h-1.5 rounded bg-[var(--c-series-1)]"
                style={{ width: `${Math.round(f.importance * 100)}%` }}
              />
            </span>
            <span className="w-9 text-right text-gray-500">
              {Math.round(f.importance * 100)}%
            </span>
          </li>
        );
      })}
    </ul>
  );
}
