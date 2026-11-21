// The SillyTherin page: one app built from index.html into dist/, files under dist/assets/.
// `npm run dev` serves it on port 5173 and sends the chat socket to the app on port 8000,
// which accepts this page only when started with --dev.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

const APP = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": resolve(__dirname, "src") } },
  build: {
    outDir: resolve(__dirname, "dist"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/ws": { target: APP, ws: true, changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://127.0.0.1:8000/" } }, // the app's own address, so storage works
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/panel/test/setup.ts"],
  },
});
