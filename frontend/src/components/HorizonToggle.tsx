"use client";

const HORIZONS = [7, 14, 30] as const;

export function HorizonToggle({
  value,
  onChange,
}: {
  value: number;
  onChange: (h: number) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Forecast horizon"
      className="inline-flex rounded-lg border border-gray-300 bg-white p-0.5"
    >
      {HORIZONS.map((h) => (
        <button
          key={h}
          role="radio"
          aria-checked={value === h}
          onClick={() => onChange(h)}
          className={`rounded-md px-3 py-1 text-sm font-medium ${
            value === h ? "bg-[var(--c-series-1)] text-white" : "text-gray-600"
          }`}
        >
          {h}d
        </button>
      ))}
    </div>
  );
}
