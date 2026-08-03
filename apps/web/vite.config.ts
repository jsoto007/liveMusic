import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy the API in dev so the browser talks to ONE origin. That keeps the
    // httpOnly refresh cookie first-party — a cross-site setup would have it
    // dropped and the session would end on every reload.
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_URL ?? "http://127.0.0.1:5001",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
