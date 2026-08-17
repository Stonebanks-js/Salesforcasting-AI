import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  pathname: "/dashboard",
  getSession: vi.fn(),
  getProfile: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: vi.fn() }),
  usePathname: () => mocks.pathname,
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: mocks.getSession,
      signOut: vi.fn(),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}));

// Keep the real ApiError so status-code branching is exercised for real.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getProfile: mocks.getProfile };
});

vi.mock("@/components/SignalHealthStrip", () => ({
  SignalHealthStrip: () => null,
}));

import { ApiError } from "@/lib/api";
import { AppShell } from "@/components/AppShell";

const problem = (status: number, detail: string) => ({
  type: "about:blank",
  title: detail,
  status,
  detail,
});

describe("AppShell — onboarding gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.pathname = "/dashboard";
    mocks.getSession.mockResolvedValue({
      data: { session: { access_token: "jwt" } },
    });
  });

  it("sends a signed-in user with no profile to onboarding", async () => {
    mocks.getProfile.mockRejectedValue(
      new ApiError(404, problem(404, "Profile not found; complete onboarding")),
    );
    render(
      <AppShell>
        <p>dashboard</p>
      </AppShell>,
    );
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/onboarding"));
  });

  it("renders the app when a profile exists", async () => {
    mocks.getProfile.mockResolvedValue({ country_code: "US" });
    render(
      <AppShell>
        <p>dashboard</p>
      </AppShell>,
    );
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
    expect(mocks.replace).not.toHaveBeenCalledWith("/onboarding");
  });

  it("does not gate the onboarding page itself, so the redirect can terminate", async () => {
    mocks.pathname = "/onboarding";
    mocks.getProfile.mockRejectedValue(
      new ApiError(404, problem(404, "Profile not found; complete onboarding")),
    );
    render(
      <AppShell>
        <p>onboarding form</p>
      </AppShell>,
    );
    expect(await screen.findByText("onboarding form")).toBeInTheDocument();
    expect(mocks.getProfile).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalledWith("/onboarding");
  });

  it("treats an unreachable API as an error, not as 'not onboarded'", async () => {
    // A 500, a CORS rejection or a bad base URL must never be read as a
    // missing profile — that would strand the user where the save also fails.
    mocks.getProfile.mockRejectedValue(
      new ApiError(500, problem(500, "Internal Server Error")),
    );
    render(
      <AppShell>
        <p>dashboard</p>
      </AppShell>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't reach TrendCast/i);
    expect(mocks.replace).not.toHaveBeenCalledWith("/onboarding");
  });

  it("redirects to login when there is no session", async () => {
    mocks.getSession.mockResolvedValue({ data: { session: null } });
    render(
      <AppShell>
        <p>dashboard</p>
      </AppShell>,
    );
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
    expect(mocks.getProfile).not.toHaveBeenCalled();
  });
});
