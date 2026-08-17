"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, getProfile } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { SignalHealthStrip } from "./SignalHealthStrip";

const ONBOARDING_PATH = "/onboarding";

/**
 * "checking"     — resolving session + profile
 * "ready"        — authenticated, and onboarded (or on the onboarding page)
 * "unreachable"  — authenticated, but the API did not answer
 *
 * A missing profile is deliberately NOT a state here: it resolves to a
 * redirect, since /onboarding is the only thing that can create one.
 */
type GateState = "checking" | "ready" | "unreachable";

/** Auth- and onboarding-guarded app shell: nav, signal health strip, sign-out. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<GateState>("checking");
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => {
    setState("checking");
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) router.replace("/login");
    });
    return () => subscription.unsubscribe();
  }, [router]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (cancelled) return;
      if (!session) {
        router.replace("/login");
        return;
      }

      // The onboarding page is what creates the profile, so it must never be
      // gated on having one — that would be an unbreakable redirect loop.
      if (pathname === ONBOARDING_PATH) {
        setState("ready");
        return;
      }

      try {
        await getProfile();
        if (!cancelled) setState("ready");
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          // Signed up but never onboarded. No database trigger creates this
          // row; PUT /profile is the only path, and it lives on /onboarding.
          router.replace(ONBOARDING_PATH);
          return;
        }
        // Anything else — offline, CORS, a bad base URL, a cold Render dyno —
        // must not be mistaken for "not onboarded". Bouncing the user to
        // onboarding would strand them somewhere the save will also fail.
        setState("unreachable");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [router, pathname, attempt]);

  if (state === "checking") {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        role="status"
        aria-live="polite"
      >
        <span className="text-[var(--c-muted)]">Loading your workspace…</span>
      </div>
    );
  }

  if (state === "unreachable") {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div
          role="alert"
          className="w-full max-w-md rounded-xl border border-[var(--c-rule)] bg-[var(--c-surface)] p-6 text-center"
        >
          <h1 className="mb-2 text-lg font-semibold text-[var(--c-ink)]">
            We can&apos;t reach TrendCast right now
          </h1>
          <p className="mb-1 text-sm text-[var(--c-ink-soft)]">
            You&apos;re signed in, but the server didn&apos;t answer. This is usually a
            brief connection problem.
          </p>
          <p className="mb-5 text-sm text-[var(--c-muted)]">
            If it keeps happening, the API address or allowed origins may be
            misconfigured for this deployment.
          </p>
          <div className="flex justify-center gap-2">
            <button
              onClick={retry}
              className="rounded-lg bg-[var(--c-brand)] px-4 py-2 text-sm font-semibold text-[var(--c-on-brand)] transition-colors hover:bg-[var(--c-brand-hover)]"
            >
              Try again
            </button>
            <button
              onClick={async () => {
                await supabase.auth.signOut();
                router.replace("/login");
              }}
              className="rounded-lg border border-[var(--c-rule)] px-4 py-2 text-sm text-[var(--c-ink-soft)]"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }

  // During onboarding there is nowhere useful to navigate yet, so the shell
  // stays deliberately bare.
  const onboarding = pathname === ONBOARDING_PATH;
  const nav = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/upload", label: "Data" },
    { href: "/settings", label: "Settings" },
  ];

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-[var(--c-surface)] focus:p-2"
      >
        Skip to content
      </a>
      <header className="border-b border-[var(--c-rule)] bg-[var(--c-surface)]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <span className="text-lg font-bold text-[var(--c-brand)]">TrendCast AI</span>
          {!onboarding && (
            <nav aria-label="Main" className="flex gap-1">
              {nav.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={pathname === n.href ? "page" : undefined}
                  className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                    pathname === n.href
                      ? "bg-[var(--c-brand)] text-[var(--c-on-brand)]"
                      : "text-[var(--c-ink-soft)] hover:bg-[var(--c-raised)]"
                  }`}
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          )}
          <div className="ml-auto flex items-center gap-4">
            {!onboarding && <SignalHealthStrip />}
            <button
              onClick={async () => {
                await supabase.auth.signOut();
                router.replace("/login");
              }}
              className="text-sm text-[var(--c-muted)] transition-colors hover:text-[var(--c-ink)]"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-6">
        {children}
      </main>
    </div>
  );
}
