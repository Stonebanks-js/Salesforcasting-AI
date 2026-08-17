import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  signUp: vi.fn(),
  signIn: vi.fn(),
  getSession: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: vi.fn() }),
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: mocks.getSession,
      signUp: mocks.signUp,
      signInWithPassword: mocks.signIn,
    },
  },
}));

import LoginPage from "@/app/login/page";

type User = ReturnType<typeof userEvent.setup>;

async function fillAndSubmit(user: User, label: string) {
  await user.type(screen.getByLabelText(/email/i), "owner@example.com");
  await user.type(screen.getByLabelText(/password/i), "hunter22");
  await user.click(screen.getByRole("button", { name: label }));
}

// jsdom start-up plus a full React render puts the first case in this file
// well past vitest's 5s default on a cold run.
const SLOW = 20_000;

describe("login page — post-signup routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Nobody is signed in when the page mounts.
    mocks.getSession.mockResolvedValue({ data: { session: null } });
  });

  it(
    "routes to onboarding when sign-up returns a live session",
    async () => {
      // Email confirmation disabled => Supabase issues a session immediately.
      mocks.signUp.mockResolvedValue({
        data: { session: { access_token: "jwt" } },
        error: null,
      });
      const user = userEvent.setup();
      render(<LoginPage />);
      await user.click(screen.getByRole("tab", { name: /sign up/i }));
      await fillAndSubmit(user, "Create account");

      await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/onboarding"));
    },
    SLOW,
  );

  it(
    "never tells a signed-in user to go and check their email",
    async () => {
      mocks.signUp.mockResolvedValue({
        data: { session: { access_token: "jwt" } },
        error: null,
      });
      const user = userEvent.setup();
      render(<LoginPage />);
      await user.click(screen.getByRole("tab", { name: /sign up/i }));
      await fillAndSubmit(user, "Create account");

      await waitFor(() => expect(mocks.replace).toHaveBeenCalled());
      expect(screen.queryByText(/check your email/i)).not.toBeInTheDocument();
    },
    SLOW,
  );

  it(
    "shows a confirmation notice, naming the address, when no session is returned",
    async () => {
      // Email confirmation enabled => no session until the link is opened.
      mocks.signUp.mockResolvedValue({ data: { session: null }, error: null });
      const user = userEvent.setup();
      render(<LoginPage />);
      await user.click(screen.getByRole("tab", { name: /sign up/i }));
      await fillAndSubmit(user, "Create account");

      const notice = await screen.findByRole("status");
      expect(notice).toHaveTextContent(/owner@example\.com/);
      expect(mocks.replace).not.toHaveBeenCalledWith("/onboarding");
    },
    SLOW,
  );

  it(
    "translates opaque auth errors into an actionable message",
    async () => {
      mocks.signIn.mockResolvedValue({
        error: { message: "Invalid login credentials" },
      });
      const user = userEvent.setup();
      render(<LoginPage />);
      await fillAndSubmit(user, "Sign in");

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/don't match an account/i);
    },
    SLOW,
  );
});
