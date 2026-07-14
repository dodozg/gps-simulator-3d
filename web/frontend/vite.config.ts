import { defineConfig } from "vite";
import cesium from "vite-plugin-cesium";

// Frontend dev server proxira /api i /ws na FastAPI backend (uvicorn :8000).
// U produkciji backend poslužuje buildani dist na istom originu, pa proxy nije nužan.
export default defineConfig({
  plugins: [cesium()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, target: "es2020" },
});
