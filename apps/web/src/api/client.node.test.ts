// @vitest-environment node

import { describe, expect, it, vi } from "vitest";

import { api, createApiClient } from "./client";

describe("typed API client outside a browser", () => {
  it("accepts an explicit absolute base URL and injected fetch", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (_input, _init) =>
      new Response(null, { status: 204 })
    );
    const client = createApiClient({
      baseUrl: "https://api.example.test",
      fetch: fetchMock,
    });

    await client.GET("/health/live", {});

    const request = fetchMock.mock.calls[0]![0] as Request;
    expect(request.url).toBe("https://api.example.test/health/live");
    expect(request.credentials).toBe("same-origin");
  });

  it("fails early with a safe configuration error when no base URL exists", () => {
    expect(() => createApiClient({ fetch: vi.fn() })).toThrowError(
      "API client requires an absolute HTTP(S) base URL outside a browser."
    );
  });

  it("fails safely before a Node caller can use the browser singleton", () => {
    expect(() => api.GET).toThrowError(
      "API client requires an absolute HTTP(S) base URL outside a browser."
    );
  });

  it.each(["", "/api", "api.example.test", "ftp://api.example.test"])(
    "rejects invalid base URL configuration: %s",
    (baseUrl) => {
      expect(() => createApiClient({ baseUrl, fetch: vi.fn() })).toThrowError(
        "API client base URL must be an absolute HTTP(S) URL."
      );
    }
  );
});
