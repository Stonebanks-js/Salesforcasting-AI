"use client";

import { useState } from "react";
import useSWR from "swr";
import { AppShell } from "@/components/AppShell";
import {
  addAsin,
  ApiError,
  deleteAsin,
  deleteCalendarEvent,
  getAsins,
  getCalendarEvents,
  getProfile,
  getSignalSettings,
  patchSignalSettings,
  putProfile,
} from "@/lib/api";
import { SIGNAL_META } from "@/lib/signals";
import type { Signal } from "@/lib/types";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5">
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function ProfileSection() {
  const { data: profile, mutate } = useSWR("/profile", getProfile, {
    shouldRetryOnError: false,
  });
  const [saved, setSaved] = useState(false);

  if (!profile) return <p className="text-sm text-gray-400">Loading profile…</p>;

  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        await putProfile({
          business_name: String(form.get("business_name") ?? "") || null,
          country_code: String(form.get("country_code") ?? profile.country_code),
          city: String(form.get("city") ?? "") || null,
          latitude: profile.latitude,
          longitude: profile.longitude,
          timezone: profile.timezone,
          currency: profile.currency,
        });
        setSaved(true);
        mutate();
        setTimeout(() => setSaved(false), 3000);
      }}
    >
      <label className="text-sm">
        <span className="mb-1 block text-gray-600">Business name</span>
        <input
          name="business_name"
          defaultValue={profile.business_name ?? ""}
          className="w-full rounded-lg border border-gray-300 px-3 py-2"
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block text-gray-600">Country (ISO code)</span>
        <input
          name="country_code"
          defaultValue={profile.country_code}
          maxLength={2}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 uppercase"
        />
      </label>
      <label className="text-sm">
        <span className="mb-1 block text-gray-600">City</span>
        <input
          name="city"
          defaultValue={profile.city ?? ""}
          className="w-full rounded-lg border border-gray-300 px-3 py-2"
        />
      </label>
      <div className="flex items-end">
        <button className="rounded-lg bg-[var(--c-series-1)] px-4 py-2 text-sm font-medium text-white">
          Save
        </button>
        {saved && (
          <span role="status" className="ml-2 text-sm text-green-700">
            Saved ✓
          </span>
        )}
      </div>
    </form>
  );
}

function SignalsSection() {
  const { data, mutate } = useSWR("/signals/settings", getSignalSettings, {
    shouldRetryOnError: false,
  });
  const items = data?.items ?? [];

  const toggle = async (signal: Signal, enabled: boolean) => {
    await patchSignalSettings({ [signal]: enabled });
    mutate();
  };

  return (
    <ul className="space-y-2">
      {items.map((s) => (
        <li key={s.signal} className="flex items-center justify-between gap-3">
          <span>
            <span className="block text-sm font-medium">
              {SIGNAL_META[s.signal].label}
            </span>
            <span className="block text-xs text-gray-500">
              {SIGNAL_META[s.signal].description}
            </span>
          </span>
          <button
            role="switch"
            aria-checked={s.enabled}
            aria-label={`Toggle ${SIGNAL_META[s.signal].label}`}
            onClick={() => toggle(s.signal, !s.enabled)}
            className={`relative h-6 w-11 rounded-full transition-colors ${
              s.enabled ? "bg-[var(--c-series-1)]" : "bg-gray-300"
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                s.enabled ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </button>
        </li>
      ))}
    </ul>
  );
}

function MarketplaceSection() {
  const { data, mutate } = useSWR("/marketplace/asins", getAsins, {
    shouldRetryOnError: false,
  });
  const [asin, setAsin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const items = data?.items ?? [];

  const add = async () => {
    setError(null);
    try {
      await addAsin(asin.toUpperCase());
      setAsin("");
      mutate();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to add ASIN");
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">
        Track Amazon price & sales-rank for your products (Keepa free tier).{" "}
        <strong>{items.length} of 10 used.</strong>
      </p>
      <div className="h-1.5 w-full rounded bg-gray-100">
        <div
          className="h-1.5 rounded bg-[var(--c-series-2)]"
          style={{ width: `${(items.length / 10) * 100}%` }}
        />
      </div>
      <div className="flex gap-2">
        <input
          value={asin}
          onChange={(e) => setAsin(e.target.value)}
          placeholder="B08XYZ1234"
          maxLength={10}
          aria-label="ASIN"
          className="w-40 rounded-lg border border-gray-300 px-3 py-1.5 text-sm uppercase"
        />
        <button
          onClick={add}
          disabled={asin.length !== 10 || items.length >= 10}
          className="rounded-lg bg-[var(--c-series-1)] px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          Track
        </button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
      <ul className="space-y-1">
        {items.map((a) => (
          <li
            key={a.asin}
            className="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5 text-sm"
          >
            {a.asin}
            <button
              onClick={async () => {
                await deleteAsin(a.asin);
                mutate();
              }}
              className="text-xs text-red-500 hover:underline"
              aria-label={`Stop tracking ${a.asin}`}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CalendarSection() {
  const { data, mutate } = useSWR("/calendar/events", getCalendarEvents, {
    shouldRetryOnError: false,
  });
  const items = data?.items ?? [];

  return (
    <div className="space-y-2">
      {items.length === 0 && (
        <p className="text-sm text-gray-400">
          No school-vacation calendars uploaded. Add one on the Data page.
        </p>
      )}
      <ul className="space-y-1">
        {items.map((e) => (
          <li
            key={e.id}
            className="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5 text-sm"
          >
            <span>
              {e.label}{" "}
              <span className="text-gray-500">
                ({e.start_date} → {e.end_date})
              </span>
            </span>
            <button
              onClick={async () => {
                await deleteCalendarEvent(e.id);
                mutate();
              }}
              className="text-xs text-red-500 hover:underline"
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <AppShell>
      <h1 className="mb-4 text-2xl font-bold">Settings</h1>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Business profile">
          <ProfileSection />
        </Section>
        <Section title="External signals">
          <SignalsSection />
        </Section>
        <Section title="Amazon marketplace tracking">
          <MarketplaceSection />
        </Section>
        <Section title="School vacations">
          <CalendarSection />
        </Section>
      </div>
    </AppShell>
  );
}
