import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development, /api is proxied to the FastAPI backend so no CORS setup is needed.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { rollupOptions: { output: { manualChunks: { charts: ["recharts"], vendor: ["react", "react-dom", "react-router-dom"] } } } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
