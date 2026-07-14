import { defineConfig } from "vite";
import cesium from "vite-plugin-cesium";

// Frontend dev server proxira /api i /ws na FastAPI backend (uvicorn :8010).
// U produkciji backend poslužuje buildani dist na istom originu, pa proxy nije nužan.
// Port je promjenjiv preko GPSWEB_PORT (default 8010; 8000 zauzima druga app).
const BACKEND_PORT = process.env.GPSWEB_PORT || "8010";
export default defineConfig({
  plugins: [cesium()],
  server: {
    port: 5173,
    proxy: {
      "/api": `http://127.0.0.1:${BACKEND_PORT}`,
      "/ws": { target: `ws://127.0.0.1:${BACKEND_PORT}`, ws: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, target: "es2020" },
});
