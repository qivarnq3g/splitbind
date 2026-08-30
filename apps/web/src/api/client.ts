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

export function createApiClient(fetchImpl: typeof globalThis.fetch = globalThis.fetch) {
  const client = createClient<BrowserPaths>({
    baseUrl: typeof window === "undefined" ? "" : window.location.origin,
    credentials: "same-origin",
    fetch: fetchImpl,
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

export const api = createApiClient();
