import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getForecasts, getProducts } from "@/lib/api";

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: "test-jwt" } },
      })),
    },
  },
}));

describe("api client", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches the Supabase JWT to requests", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await getProducts();
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer test-jwt",
    );
  });

  it("throws ApiError with problem detail on non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              type: "about:blank",
              title: "Not found",
              status: 404,
              detail: "sku_not_found: NOPE",
            }),
            { status: 404 },
          ),
      ),
    );
    await expect(getForecasts(["NOPE"], 30)).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "sku_not_found: NOPE",
    });
    expect(ApiError).toBeDefined();
  });
});
