import type { Signal } from "./types";

export const SIGNAL_META: Record<
  Signal,
  { label: string; description: string; note?: string }
> = {
  weather: {
    label: "Weather",
    description: "Temperature, precipitation and conditions at your location.",
  },
  holidays: {
    label: "Public holidays",
    description: "National and regional holidays for your country.",
  },
  trends: {
    label: "Search trends",
    description: "Consumer search interest for your product categories.",
    note: "Unofficial source — may occasionally be delayed.",
  },
  macro: {
    label: "Economic indicators",
    description: "Inflation, consumer sentiment and spending (FRED).",
  },
  events: {
    label: "Local events",
    description: "Concerts, sports and festivals near you (Ticketmaster).",
  },
  marketplace: {
    label: "Amazon marketplace",
    description: "Price and sales-rank history for products you track (Keepa).",
    note: "Optional — up to 10 products (free-tier limit).",
  },
};
