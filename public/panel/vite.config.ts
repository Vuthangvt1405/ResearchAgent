// Library build: one ES module + one CSS file in public/build/ with fixed names,
// loaded same-origin by public/custom.js (plan §4.1, SEC3).
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  resolve: { alias: { "@": resolve(__dirname, "src") } },
  // Library mode leaves process.env in React; only the build needs it replaced
  define: command === "build" ? { "process.env.NODE_ENV": JSON.stringify("production") } : {},
  build: {
    outDir: resolve(__dirname, "../build"),
    emptyOutDir: true,
    cssCodeSplit: false,
    // A plain app build of one entry (library mode would skip minifying whitespace)
    rollupOptions: {
      input: resolve(__dirname, "src/main.tsx"),
      output: { format: "es", entryFileNames: "notebook-panel.js", assetFileNames: "notebook-panel[extname]", inlineDynamicImports: true },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
  },
}));
