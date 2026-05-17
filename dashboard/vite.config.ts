import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/run": "http://localhost:8080",
      "/events": "http://localhost:8080",
      "/runs": "http://localhost:8080",
      "/health": "http://localhost:8080",
    },
  },
});
