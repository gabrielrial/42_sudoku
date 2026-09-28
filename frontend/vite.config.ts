import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is proxied so the browser only ever talks to one origin in
// development. That keeps the session cookie same-site and means the CSRF
// origin check behaves the same locally as it will in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_TARGET ?? "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
});
