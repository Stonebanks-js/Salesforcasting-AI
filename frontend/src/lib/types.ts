/** API types mirroring api_contracts.md v1.0 */

export type Signal =
  | "weather"
  | "holidays"
  | "trends"
  | "macro"
  | "events"
  | "marketplace";

export const SIGNALS: Signal[] = [
  "weather",
  "holidays",
  "trends",
  "macro",
  "events",
  "marketplace",
];

export interface Profile {
  business_name: string | null;
  country_code: string;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string;
  currency: string;
  onboarding_complete: boolean;
}

export interface ProductItem {
  sku: string;
  product_name: string;
  category: string | null;
  sales_days: number;
  last_sale_date: string | null;
  has_forecast: boolean;
}

export interface ForecastPoint {
  date: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
}

export interface Factor {
  factor: string;
  importance: number;
  direction: "up" | "down" | "neutral" | null;
}

export interface ForecastSeries {
  sku: string;
  model_version: string;
  mape_backtest: number | null;
  degraded: boolean;
  points: ForecastPoint[];
  factors: Factor[];
}

export interface SignalHealth {
  signal: string;
  status: "live" | "stale" | "degraded" | "disabled";
  last_success_at: string | null;
  quota_note?: string | null;
}

export interface ForecastResponse {
  model_run_id: string;
  generated_at: string;
  series: ForecastSeries[];
  signal_health: SignalHealth[];
}

export interface UploadAccepted {
  upload_id: string;
  status: "pending";
  status_url: string;
}

export interface RowError {
  row: number;
  field: string;
  message: string;
}

export interface UploadStatus {
  id: string;
  kind: "sales" | "calendar";
  status: "pending" | "validated" | "loaded" | "failed";
  row_count: number | null;
  error_report: { rejected_rows?: RowError[] } | null;
  created_at: string | null;
}

export interface SignalSetting {
  signal: Signal;
  enabled: boolean;
}

export interface AsinItem {
  asin: string;
  created_at: string | null;
}

export interface CalendarEventItem {
  id: number;
  label: string;
  start_date: string;
  end_date: string;
}

export interface SalesPoint {
  date: string;
  quantity: number;
  revenue: number | null;
  promo_flag: boolean;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string | null;
  errors?: unknown[];
}
