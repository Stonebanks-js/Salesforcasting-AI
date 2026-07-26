/** Typed API client for the TrendCast FastAPI backend.
 *
 * Attaches the user's Supabase JWT as a Bearer token; the backend derives
 * user_id from the token (never from request params).
 */
import { supabase } from "./supabase";
import type {
  AsinItem,
  CalendarEventItem,
  ForecastResponse,
  Problem,
  ProductItem,
  Profile,
  SalesPoint,
  SignalSetting,
  UploadAccepted,
  UploadStatus,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public problem: Problem,
  ) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
  }
}

async function authedFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) {
    throw new ApiError(401, {
      type: "about:blank",
      title: "Not authenticated",
      status: 401,
      detail: "Please sign in",
    });
  }
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  if (!resp.ok) {
    let problem: Problem;
    try {
      problem = (await resp.json()) as Problem;
    } catch {
      problem = {
        type: "about:blank",
        title: resp.statusText,
        status: resp.status,
        detail: null,
      };
    }
    throw new ApiError(resp.status, problem);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// --- Profile ---
export const getProfile = () => authedFetch<Profile>("/profile");
export const putProfile = (body: Partial<Profile>) =>
  authedFetch<Profile>("/profile", { method: "PUT", body: JSON.stringify(body) });

// --- Products & sales ---
export const getProducts = (search?: string) =>
  authedFetch<{ items: ProductItem[]; total: number }>(
    `/products?limit=200${search ? `&search=${encodeURIComponent(search)}` : ""}`,
  );
export const getSales = (sku: string) =>
  authedFetch<{ sku: string; items: SalesPoint[] }>(
    `/sales?sku=${encodeURIComponent(sku)}`,
  );

// --- Forecasts ---
export const getForecasts = (skus: string[], horizon: number) =>
  authedFetch<ForecastResponse>(
    `/forecasts?skus=${skus.map(encodeURIComponent).join(",")}&horizon=${horizon}`,
  );

// --- Signals ---
export const getSignalSettings = () =>
  authedFetch<{ items: SignalSetting[] }>("/signals/settings");
export const patchSignalSettings = (patch: Partial<Record<string, boolean>>) =>
  authedFetch<{ items: SignalSetting[] }>("/signals/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
export const getSignalStatus = () =>
  authedFetch<{ items: { signal: string; status: string; last_success_at: string | null }[] }>(
    "/signals/status",
  );

// --- Uploads ---
export const uploadSales = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return authedFetch<UploadAccepted>("/uploads/sales", {
    method: "POST",
    body: form,
  });
};
export const uploadCalendar = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return authedFetch<UploadAccepted>("/uploads/calendar", {
    method: "POST",
    body: form,
  });
};
export const getUpload = (id: string) => authedFetch<UploadStatus>(`/uploads/${id}`);

// --- Marketplace ---
export const getAsins = () => authedFetch<{ items: AsinItem[] }>("/marketplace/asins");
export const addAsin = (asin: string) =>
  authedFetch<{ asin: string }>("/marketplace/asins", {
    method: "POST",
    body: JSON.stringify({ asin }),
  });
export const deleteAsin = (asin: string) =>
  authedFetch<void>(`/marketplace/asins/${encodeURIComponent(asin)}`, {
    method: "DELETE",
  });

// --- Calendar ---
export const getCalendarEvents = () =>
  authedFetch<{ items: CalendarEventItem[] }>("/calendar/events");
export const deleteCalendarEvent = (id: number) =>
  authedFetch<void>(`/calendar/events/${id}`, { method: "DELETE" });
