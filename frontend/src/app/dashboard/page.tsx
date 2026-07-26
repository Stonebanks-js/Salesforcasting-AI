"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import useSWR from "swr";
import { AppShell } from "@/components/AppShell";
import { ForecastCard } from "@/components/ForecastCard";
import { HorizonToggle } from "@/components/HorizonToggle";
import { SkuMultiSelect } from "@/components/SkuMultiSelect";
import { ApiError, getForecasts, getProducts } from "@/lib/api";

function DashboardInner() {
  const router = useRouter();
  const params = useSearchParams();

  const selectedSkus = useMemo(
    () => (params.get("skus") ?? "").split(",").filter(Boolean),
    [params],
  );
  const horizon = Number(params.get("horizon") ?? "30");

  const setState = (skus: string[], h: number) => {
    const q = new URLSearchParams();
    if (skus.length) q.set("skus", skus.join(","));
    q.set("horizon", String(h));
    router.replace(`/dashboard?${q.toString()}`, { scroll: false });
  };

  const { data: products } = useSWR("/products", () => getProducts());
  const productBySku = useMemo(
    () => new Map((products?.items ?? []).map((p) => [p.sku, p])),
    [products],
  );

  const {
    data: forecasts,
    error,
    isLoading,
  } = useSWR(
    selectedSkus.length ? ["forecasts", selectedSkus.join(","), horizon] : null,
    () => getForecasts(selectedSkus, horizon),
    { shouldRetryOnError: false },
  );

  const apiError = error instanceof ApiError ? error : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-72 flex-1">
          <SkuMultiSelect
            products={products?.items ?? []}
            selected={selectedSkus}
            onChange={(skus) => setState(skus, horizon)}
            loading={!products}
          />
        </div>
        <HorizonToggle value={horizon} onChange={(h) => setState(selectedSkus, h)} />
        {forecasts && (
          <span className="text-xs text-gray-400">
            Last run: {new Date(forecasts.generated_at).toLocaleString()}
          </span>
        )}
      </div>

      {selectedSkus.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
          <p className="text-gray-600">
            Select up to 10 products above to compare their demand forecasts
            side-by-side.
          </p>
          <p className="mt-2 text-sm text-gray-400">
            No products yet?{" "}
            <Link href="/upload" className="text-[var(--c-series-1)] underline">
              Upload your sales data
            </Link>{" "}
            or generate demo data.
          </p>
        </div>
      )}

      {isLoading && selectedSkus.length > 0 && (
        <p role="status" className="text-sm text-gray-500">
          Loading forecasts…
        </p>
      )}

      {apiError && (
        <div role="alert" className="rounded-lg bg-amber-50 p-4 text-sm text-amber-800">
          {apiError.status === 404 && apiError.message.includes("nightly batch") ? (
            <>
              Forecasts aren&apos;t ready yet — they&apos;re computed by the nightly
              batch job after your first data upload.{" "}
              <Link href="/upload" className="underline">
                Upload data
              </Link>
            </>
          ) : (
            apiError.message
          )}
        </div>
      )}

      {forecasts && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {forecasts.series.map((s, i) => (
            <ForecastCard
              key={s.sku}
              series={s}
              product={productBySku.get(s.sku)}
              colorIndex={i}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="text-sm text-gray-500">Loading…</p>}>
        <DashboardInner />
      </Suspense>
    </AppShell>
  );
}
