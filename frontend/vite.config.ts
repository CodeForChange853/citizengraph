import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";
import tokens from "./src/design/tokens.json" with { type: "json" };

const BLUE = tokens.palette["blue-500"].hex;
const PAGE_BG = tokens.palette["gray-25"].hex;

// Dev: the app talks to /api/*, proxied to the FastAPI mock (uvicorn citizengraph.api.main:app).
// If the API is down the app falls back to local fixtures (see src/api/client.ts).
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // The service worker updates itself; the new version is used on the next visit.
      registerType: "autoUpdate",
      includeAssets: ["icon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "Citizen Graph",
        short_name: "Citizen Graph",
        description:
          "What to bring, what it costs and where to go for city services. Thesis prototype, not an official government app.",
        lang: "en",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: PAGE_BG,
        theme_color: BLUE,
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
          { src: "icon.svg", sizes: "any", type: "image/svg+xml" },
        ],
      },
      workbox: {
        // App shell: scripts, styles, fonts, icons and the page itself, so the app opens with no signal.
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        // The landing page (/welcome), its 3D chunk and its fonts are not part of the app shell:
        // they are fetched only on /welcome and cached then (runtimeCaching below).
        globIgnores: ["**/Landing-*", "**/Stage3D-*", "**/archivo-*", "**/atkinson-hyperlegible-mono-*"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            // Landing assets have hashed names, so a cached copy never goes stale.
            urlPattern: ({ url }) => /^\/assets\/(Landing|Stage3D|archivo|atkinson-hyperlegible-mono)-/.test(url.pathname),
            handler: "CacheFirst",
            options: { cacheName: "landing", expiration: { maxEntries: 40 } },
          },
          {
            // The service list is a GET: show the last copy while a fresh one loads.
            // POST /chat is never cached; the last answers are kept on the device by chatStore.
            urlPattern: ({ url }) => url.pathname === "/api/services",
            handler: "StaleWhileRevalidate",
            options: { cacheName: "api-services", expiration: { maxEntries: 5, maxAgeSeconds: 7 * 24 * 3600 } },
          },
        ],
      },
    }),
  ],
  build: { chunkSizeWarningLimit: 600 }, // one 530 kB chunk (164 kB gzip) is fine for an app shell that is cached
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
