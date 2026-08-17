"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

/** Supabase auth messages are terse and occasionally cryptic; say what to do next. */
function friendlyAuthError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("invalid login credentials")) {
    return "That email and password don't match an account. Check for typos, or sign up instead.";
  }
  if (m.includes("email not confirmed")) {
    return "This account still needs confirming. Open the link in your email, then sign in.";
  }
  if (m.includes("user already registered") || m.includes("already been registered")) {
    return "An account with this email already exists. Switch to Sign in.";
  }
  if (m.includes("password should be")) {
    return "Password must be at least 6 characters.";
  }
  if (m.includes("rate limit") || m.includes("too many")) {
    return "Too many attempts. Wait a minute, then try again.";
  }
  if (m.includes("fetch") || m.includes("network")) {
    return "Couldn't reach the authentication service. Check your connection and try again.";
  }
  return message;
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) router.replace("/dashboard");
    });
  }, [router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    if (mode === "signin") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) setError(friendlyAuthError(error.message));
      else router.replace("/dashboard");
    } else {
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) {
        setError(friendlyAuthError(error.message));
      } else if (data.session) {
        // Email confirmation is disabled for the pilot, so sign-up returns a
        // live session. Send them straight on — telling someone who is already
        // authenticated to go and check their email strands them here.
        router.replace("/onboarding");
      } else {
        // Confirmation is enabled: no session until the link is opened.
        setNotice(`Account created. We sent a confirmation link to ${email}. Open it, then sign in.`);
        setMode("signin");
      }
    }
    setBusy(false);
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="mb-1 text-xl font-bold text-[var(--c-series-1)]">TrendCast AI</h1>
        <p className="mb-4 text-sm text-gray-500">
          Demand forecasting with real-world signals
        </p>

        <div className="mb-4 flex rounded-lg bg-gray-100 p-0.5" role="tablist">
          {(["signin", "signup"] as const).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={`flex-1 rounded-md py-1 text-sm font-medium ${
                mode === m ? "bg-white shadow-sm" : "text-gray-500"
              }`}
            >
              {m === "signin" ? "Sign in" : "Sign up"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
              autoComplete="email"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">Password</span>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="text-sm text-green-700">
              {notice}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-[var(--c-series-1)] py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? "…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
