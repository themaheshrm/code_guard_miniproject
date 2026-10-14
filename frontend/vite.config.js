import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000" } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("@monaco-editor")) return "vendor-monaco";
            if (id.includes("d3-") || id.includes("victory-vendor")) return "vendor-d3";
            if (id.includes("recharts")) return "vendor-recharts";
            if (id.includes("react") || id.includes("scheduler")) return "vendor-react";
          }
        },
      },
    },
  },

});

