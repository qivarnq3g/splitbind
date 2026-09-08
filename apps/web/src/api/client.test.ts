import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api as browserApi, createApiClient } from "./client";

const JOB_ID = "00000000-0000-4000-8000-000000000001";
const CORRELATION_ID = "00000000-0000-4000-8000-000000000002";

describe("typed API client", () => {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(null, { status: 204 })
  );
  let api: ReturnType<typeof createApiClient>;

  beforeEach(() => {
    fetchMock.mockClear();
    api = createApiClient({ fetch: fetchMock });
    document.cookie = "csrftoken=token%2Bwith%2Fencoding";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("uses same-origin credentials and a decoded CSRF cookie on mutations", async () => {
    await api.POST("/api/v1/jobs/{id}/cancel", {
      params: { path: { id: JOB_ID } },
      body: { correlation_id: CORRELATION_ID },
    });

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request).toBeInstanceOf(Request);
    expect(request.credentials).toBe("same-origin");
    expect(request.headers.get("X-CSRFToken")).toBe("token+with/encoding");
  });

  it("does not attach a CSRF header to safe methods", async () => {
    await api.GET("/api/v1/jobs/{id}", { params: { path: { id: JOB_ID } } });

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.credentials).toBe("same-origin");
    expect(request.headers.has("X-CSRFToken")).toBe(false);
  });

  it("omits the CSRF header when the cookie is absent", async () => {
    document.cookie = "csrftoken=; Max-Age=0";

    await api.POST("/api/v1/jobs/{id}/cancel", {
      params: { path: { id: JOB_ID } },
      body: { correlation_id: CORRELATION_ID },
    });

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.headers.has("X-CSRFToken")).toBe(false);
  });

  it("does not log request URLs", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const debug = vi.spyOn(console, "debug").mockImplementation(() => undefined);

    await api.GET("/api/v1/jobs/{id}", { params: { path: { id: JOB_ID } } });

    expect(log).not.toHaveBeenCalled();
    expect(info).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
    expect(debug).not.toHaveBeenCalled();
  });

  it("exposes a same-origin browser singleton", async () => {
    vi.stubGlobal("fetch", fetchMock);

    await browserApi.GET("/health/live", {});

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(new URL(request.url).origin).toBe(window.location.origin);
  });
});
