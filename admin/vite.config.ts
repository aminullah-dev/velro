import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The API is same-origin in production; proxying in development keeps the
    // client's base URL identical in both, so there is no CORS special case to
    // remember and no environment-specific auth behaviour.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
