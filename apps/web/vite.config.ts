import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import type { ProxyOptions } from "vite";

const LOCAL_TARGET = "http://127.0.0.1:8000";

function buildProxy(target: string): Record<string, ProxyOptions> {
  const upstream = new URL(target);
  const remote = upstream.protocol === "https:";

  const options: ProxyOptions = {
    target,
    changeOrigin: true,
    secure: true,
    timeout: 180000,
    proxyTimeout: 180000,
    configure: (proxy) => {
      proxy.on("error", (error, request) => {
        console.error(
          `[proxy] ${request.method ?? "?"} ${request.url ?? "?"} failed: ${error.message}`,
        );
      });
      proxy.on("proxyRes", (proxyResponse, request) => {
        if ((proxyResponse.statusCode ?? 0) >= 400) {
          console.error(
            `[proxy] ${request.method ?? "?"} ${request.url ?? "?"} -> ${proxyResponse.statusCode}`,
          );
        }
      });
    },
  };

  if (remote) {
    const base = options.configure;
    options.configure = (proxy, proxyOptions) => {
      base?.(proxy, proxyOptions);
      proxy.on("proxyReq", (proxyRequest) => {
        proxyRequest.setHeader("origin", upstream.origin);
        proxyRequest.setHeader("referer", `${upstream.origin}/`);
      });
      proxy.on("proxyRes", (proxyResponse) => {
        const cookies = proxyResponse.headers["set-cookie"];
        if (!cookies) return;
        proxyResponse.headers["set-cookie"] = cookies.map((cookie) =>
          cookie
            .split("; ")
            .filter(
              (part) =>
                !/^Secure$/i.test(part) && !/^Domain=/i.test(part),
            )
            .map((part) =>
              /^SameSite=/i.test(part) ? "SameSite=Lax" : part,
            )
            .join("; "),
        );
      });
    };
  }

  return { "/api": options, "/health": options };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.SPLITBIND_API_TARGET || LOCAL_TARGET;
  const proxy = buildProxy(target);

  return {
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy,
    },
    test: {
      environment: "jsdom",
    },
  };
});
