"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { putProfile } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { SIGNAL_META } from "@/lib/signals";
import { SIGNALS, type Signal } from "@/lib/types";

const COUNTRIES = [
  ["US", "United States"], ["IN", "India"], ["GB", "United Kingdom"],
  ["DE", "Germany"], ["FR", "France"], ["CA", "Canada"], ["AU", "Australia"],
  ["NL", "Netherlands"], ["ES", "Spain"], ["IT", "Italy"], ["JP", "Japan"],
  ["BR", "Brazil"], ["MX", "Mexico"], ["PL", "Poland"], ["SE", "Sweden"],
] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [businessName, setBusinessName] = useState("");
  const [country, setCountry] = useState("US");
  const [city, setCity] = useState("");
  const [toggles, setToggles] = useState<Record<Signal, boolean>>({
    weather: true, holidays: true, trends: true,
    macro: true, events: true, marketplace: false,
  });

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      // Geocode the city via Open-Meteo (free, keyless) for weather/events.
      let latitude: number | null = null;
      let longitude: number | null = null;
      let timezone = "UTC";
      if (city.trim()) {
        const geo = await fetch(
          `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1`,
        ).then((r) => r.json());
        const hit = geo?.results?.[0];
        if (hit) {
          latitude = hit.latitude;
          longitude = hit.longitude;
          timezone = hit.timezone ?? "UTC";
        }
      }
      await putProfile({
        business_name: businessName || null,
        country_code: country,
        city: city || null,
        latitude,
        longitude,
        timezone,
      });
      router.push("/upload?first=1");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save profile");
    }
    setBusy(false);
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-lg">
        <h1 className="mb-1 text-2xl font-bold">Welcome to TrendCast AI</h1>
        <p className="mb-6 text-sm text-gray-500">
          Step {step} of 2 — {step === 1 ? "your business" : "external signals"}
        </p>

        {step === 1 && (
          <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-5">
            <label className="block text-sm">
              <span className="mb-1 block text-gray-600">Business name</span>
              <input
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
                placeholder="Acme Crafts"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-gray-600">Country</span>
              <select
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
              >
                {COUNTRIES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-gray-600">
                City (used for weather & local events)
              </span>
              <input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
                placeholder="Austin"
              />
            </label>
            <button
              onClick={() => setStep(2)}
              className="w-full rounded-lg bg-[var(--c-series-1)] py-2 text-sm font-semibold text-white"
            >
              Continue
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            {SIGNALS.map((s) => (
              <label
                key={s}
                className="flex cursor-pointer items-start gap-3 rounded-xl border border-gray-200 bg-white p-4"
              >
                <input
                  type="checkbox"
                  checked={toggles[s]}
                  onChange={(e) => setToggles({ ...toggles, [s]: e.target.checked })}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm font-medium">{SIGNAL_META[s].label}</span>
                  <span className="block text-xs text-gray-500">
                    {SIGNAL_META[s].description}
                  </span>
                  {SIGNAL_META[s].note && (
                    <span className="block text-xs text-amber-600">
                      {SIGNAL_META[s].note}
                    </span>
                  )}
                </span>
              </label>
            ))}
            {error && (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={() => setStep(1)}
                className="flex-1 rounded-lg border border-gray-300 py-2 text-sm"
              >
                Back
              </button>
              <button
                onClick={submit}
                disabled={busy}
                className="flex-1 rounded-lg bg-[var(--c-series-1)] py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy ? "Saving…" : "Finish setup"}
              </button>
            </div>
            <p className="text-xs text-gray-400">
              Signal choices are applied as account defaults; you can change them anytime
              in Settings.
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
