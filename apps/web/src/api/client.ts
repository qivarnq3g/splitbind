import createClient from "openapi-fetch";

import type { paths } from "./generated/schema";

type WithoutCsrfHeader<Operation> = Operation extends { parameters: infer Parameters }
  ? Omit<Operation, "parameters"> & {
      parameters: Parameters extends { header: infer Headers }
        ? Omit<Parameters, "header"> & (keyof Omit<Headers, "X-CSRFToken"> extends never
            ? { header?: never }
            : { header: Omit<Headers, "X-CSRFToken"> })
        : Parameters;
    }
  : Operation;

type BrowserPaths = {
  [Path in keyof paths]: {
    [Method in keyof paths[Path]]: WithoutCsrfHeader<paths[Path][Method]>;
  };
};

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
const MISSING_BASE_URL_ERROR =
  "API client requires an absolute HTTP(S) base URL outside a browser.";
const INVALID_BASE_URL_ERROR = "API client base URL must be an absolute HTTP(S) URL.";

export interface ApiClientOptions {
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
}

function csrfToken(): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }
  const prefix = "csrftoken=";
  const cookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  if (!cookie) {
    return undefined;
  }
  try {
    return decodeURIComponent(cookie.slice(prefix.length)) || undefined;
  } catch {
    return undefined;
  }
}

function resolveBaseUrl(configuredBaseUrl: string | undefined): string {
  if (configuredBaseUrl === undefined && typeof window === "undefined") {
    throw new Error(MISSING_BASE_URL_ERROR);
  }
  const baseUrl = configuredBaseUrl ?? window.location.origin;
  try {
    const parsed = new URL(baseUrl);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new Error(INVALID_BASE_URL_ERROR);
    }
    return parsed.href.replace(/\/$/, "");
  } catch (error) {
    if (error instanceof Error && error.message === INVALID_BASE_URL_ERROR) {
      throw error;
    }
    throw new Error(INVALID_BASE_URL_ERROR);
  }
}

export function createApiClient(options: ApiClientOptions = {}) {
  const client = createClient<BrowserPaths>({
    baseUrl: resolveBaseUrl(options.baseUrl),
    credentials: "same-origin",
    fetch:
      options.fetch ??
      ((input: RequestInfo | URL, init?: RequestInit) => globalThis.fetch(input, init)),
  });

  client.use({
    onRequest({ request }) {
      if (!SAFE_METHODS.has(request.method.toUpperCase())) {
        const token = csrfToken();
        if (token) {
          request.headers.set("X-CSRFToken", token);
        }
      }
      return request;
    },
  });
  return client;
}

type ApiClient = ReturnType<typeof createApiClient>;
let browserClient: ApiClient | undefined;

function getBrowserClient(): ApiClient {
  if (typeof window === "undefined") {
    throw new Error(MISSING_BASE_URL_ERROR);
  }
  browserClient ??= createApiClient({ baseUrl: window.location.origin });
  return browserClient;
}

export const api = new Proxy({} as ApiClient, {
  get(_target, property, receiver) {
    return Reflect.get(getBrowserClient(), property, receiver);
  },
});
