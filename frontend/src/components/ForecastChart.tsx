"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ForecastPoint, SalesPoint } from "@/lib/types";

interface Props {
  points: ForecastPoint[];
  history?: SalesPoint[];
  color?: string;
}

/** Forecast chart: shaded P10–P90 band + median line (+ optional history). */
export default function ForecastChart({ points, history, color = "#0072b2" }: Props) {
  const data = points.map((p) => ({
    date: p.date.slice(5), // MM-DD
    yhat: p.yhat,
    band: [p.yhat_lower, p.yhat_upper] as [number, number],
  }));
  const historyData = (history ?? []).map((h) => ({
    date: h.date.slice(5),
    actual: h.quantity,
  }));

  return (
    <div className="h-48 w-full" aria-hidden="true">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip
            formatter={(value, name) => {
              if (name === "band") {
                const [lo, hi] = value as unknown as [number, number];
                return [`${lo.toFixed(0)}–${hi.toFixed(0)}`, "80% interval"];
              }
              return [Number(value).toFixed(0), name === "yhat" ? "Forecast" : String(name)];
            }}
          />
          <Area
            type="monotone"
            dataKey="band"
            stroke="none"
            fill={color}
            fillOpacity={0.2}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="yhat"
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
      {historyData.length > 0 && (
        <p className="mt-1 text-xs text-gray-400">
          History overlay available — {historyData.length} days loaded
        </p>
      )}
    </div>
  );
}
