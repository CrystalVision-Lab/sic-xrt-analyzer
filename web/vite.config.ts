import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwind from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwind()],
  server: {
    proxy: {
      "/portal-api": "http://127.0.0.1:18770",
      "/api/v1": "http://127.0.0.1:18770",
    },
  },
  build: { sourcemap: false },
});
