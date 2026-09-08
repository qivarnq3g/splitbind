import { defineConfig } from "vitest/config";

const apiTarget = process.env.VITE_API_TARGET || "https://splitbind.qivarn.id.vn";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        secure: false,
        cookieDomainRewrite: "",
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("origin", "https://splitbind.qivarn.id.vn");
            proxyReq.setHeader("referer", "https://splitbind.qivarn.id.vn/");
            proxyReq.setHeader("host", "splitbind.qivarn.id.vn");
          });
          proxy.on("proxyRes", (proxyRes) => {
            const sc = proxyRes.headers["set-cookie"];
            if (sc) {
              proxyRes.headers["set-cookie"] = sc.map((cookie) =>
                cookie
                  .replace(/;\s*secure/gi, "")
                  .replace(/;\s*domain=[^;]+/gi, "")
                  .replace(/;\s*samesite=[^;]+/gi, "; SameSite=Lax")
              );
            }
          });
        },
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        secure: false,
        cookieDomainRewrite: "",
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("origin", "https://splitbind.qivarn.id.vn");
            proxyReq.setHeader("referer", "https://splitbind.qivarn.id.vn/");
            proxyReq.setHeader("host", "splitbind.qivarn.id.vn");
          });
          proxy.on("proxyRes", (proxyRes) => {
            const sc = proxyRes.headers["set-cookie"];
            if (sc) {
              proxyRes.headers["set-cookie"] = sc.map((cookie) =>
                cookie
                  .replace(/;\s*secure/gi, "")
                  .replace(/;\s*domain=[^;]+/gi, "")
                  .replace(/;\s*samesite=[^;]+/gi, "; SameSite=Lax")
              );
            }
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
  },
});
