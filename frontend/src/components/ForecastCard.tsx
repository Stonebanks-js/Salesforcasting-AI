"use client";

import dynamic from "next/dynamic";
import type { ForecastSeries, ProductItem } from "@/lib/types";
import { DegradedBadge, MapeBadge, ModelBadge } from "./Badges";
import { FactorList } from "./FactorList";

const ForecastChart = dynamic(() => import("./ForecastChart"), {
  ssr: false,
  loading: () => (
    <div className="flex h-48 items-center justify-center text-xs text-gray-400">
      Loading chart…
    </div>
  ),
});

const CARD_COLORS = ["#0072b2", "#e69f00", "#009e73", "#d55e00", "#cc79a7"];

interface Props {
  series: ForecastSeries;
  product?: ProductItem;
  colorIndex?: number;
}

/** One SKU's forecast: chart + quality badges + driving factors + data table. */
export function ForecastCard({ series, product, colorIndex = 0 }: Props) {
  const color = CARD_COLORS[colorIndex % CARD_COLORS.length];

  return (
    <section
      aria-label={`Forecast for ${series.sku}`}
      className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
    >
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">
          {series.sku}
          {product?.product_name && (
            <span className="ml-1.5 font-normal text-gray-500">
              {product.product_name}
            </span>
          )}
        </h3>
        <span className="ml-auto flex gap-1.5">
          <MapeBadge mape={series.mape_backtest} />
          <ModelBadge version={series.model_version} />
          {series.degraded && <DegradedBadge />}
        </span>
      </header>

      {series.points.length > 0 ? (
        <>
          <div role="img" aria-label={`Forecast chart for ${series.sku}`}>
            <ForecastChart points={series.points} color={color} />
          </div>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-gray-500">
              View data as table
            </summary>
            <table className="mt-1 w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500">
                  <th className="py-0.5">Date</th>
                  <th className="py-0.5">Forecast</th>
                  <th className="py-0.5">Lower</th>
                  <th className="py-0.5">Upper</th>
                </tr>
              </thead>
              <tbody>
                {series.points.map((p) => (
                  <tr key={p.date} className="border-t border-gray-100">
                    <td className="py-0.5">{p.date}</td>
                    <td className="py-0.5">{p.yhat.toFixed(1)}</td>
                    <td className="py-0.5">{p.yhat_lower.toFixed(1)}</td>
                    <td className="py-0.5">{p.yhat_upper.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      ) : (
        <p className="py-8 text-center text-sm text-gray-400">
          No forecast points in the latest run for this horizon.
        </p>
      )}

      <footer className="mt-3 border-t border-gray-100 pt-2">
        <FactorList factors={series.factors} />
      </footer>
    </section>
  );
}
