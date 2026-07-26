import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ForecastCard } from "@/components/ForecastCard";
import type { ForecastSeries } from "@/lib/types";

// Recharts needs real layout; stub the chart in component tests.
vi.mock("@/components/ForecastChart", () => ({
  default: () => <div data-testid="chart-stub" />,
}));

const SERIES: ForecastSeries = {
  sku: "MUG-001",
  model_version: "lightgbm:3",
  mape_backtest: 14.2,
  degraded: false,
  points: [
    { date: "2026-07-27", yhat: 42, yhat_lower: 31, yhat_upper: 55 },
    { date: "2026-07-28", yhat: 43, yhat_lower: 32, yhat_upper: 56 },
  ],
  factors: [
    { factor: "trends_interest", importance: 0.31, direction: "up" },
    { factor: "days_to_holiday", importance: 0.22, direction: "down" },
  ],
};

describe("ForecastCard", () => {
  it("renders badges, factors and a chart", () => {
    render(<ForecastCard series={SERIES} />);
    expect(screen.getByText("MUG-001")).toBeInTheDocument();
    expect(screen.getByText("MAPE 14.2%")).toBeInTheDocument();
    expect(screen.getByText("lightgbm:3")).toBeInTheDocument();
    expect(screen.getByText("trends interest")).toBeInTheDocument();
    expect(screen.queryByText(/degraded/)).not.toBeInTheDocument();
  });

  it("shows the degraded badge when the series is degraded (NFR-3 UI)", () => {
    render(<ForecastCard series={{ ...SERIES, degraded: true }} />);
    expect(screen.getByText(/degraded/)).toBeInTheDocument();
  });

  it("exposes forecast data as an accessible table", async () => {
    render(<ForecastCard series={SERIES} />);
    expect(screen.getByText("View data as table")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Forecast chart for MUG-001/ })).toBeInTheDocument();
  });
});
