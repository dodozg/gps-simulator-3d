import { createReadStream, cpSync, existsSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, extname, join, resolve, sep } from "node:path";
import { defineConfig, type Plugin } from "vite";

// Frontend dev server proxira /api i /ws na FastAPI backend (uvicorn :8010).
// U produkciji backend poslužuje buildani dist na istom originu, pa proxy nije nužan.
// Port je promjenjiv preko GPSWEB_PORT (default 8010; 8000 zauzima druga app).
const BACKEND_PORT = process.env.GPSWEB_PORT || "8010";

// --- CesiumJS statički resursi -------------------------------------------------
// Cesium JS kod Vite bundla normalno (import "cesium"), ali Cesium u runtimeu
// dohvaća Web Workere, ThirdParty (draco/basis .wasm), Assets (teksture, zvjezdano
// nebo, IAU podaci) i Widgets kao zasebne datoteke s adrese CESIUM_BASE_URL.
// Zamjena za vite-plugin-cesium (nije održavan za Vite 8 / Rolldown): u buildu
// se te mape kopiraju u dist/cesium/, a u dev načinu poslužuju iz node_modules.
const CESIUM_BASE_URL = "/cesium/";
const CESIUM_DIRS = ["Workers", "ThirdParty", "Assets", "Widgets"];
const require = createRequire(import.meta.url);
const CESIUM_BUILD = join(dirname(require.resolve("cesium/package.json")), "Build", "Cesium");

const MIME: Record<string, string> = {
  ".js": "text/javascript", ".json": "application/json", ".css": "text/css",
  ".wasm": "application/wasm", ".png": "image/png", ".jpg": "image/jpeg",
  ".gif": "image/gif", ".svg": "image/svg+xml", ".xml": "application/xml",
};

function cesiumStatic(): Plugin {
  let outDir = "dist";
  return {
    name: "gpsweb-cesium-static",
    configResolved(cfg) {
      outDir = resolve(cfg.root, cfg.build.outDir);
    },
    // Dev: /cesium/<Workers|ThirdParty|Assets|Widgets>/... izravno iz node_modules.
    configureServer(server) {
      server.middlewares.use(CESIUM_BASE_URL, (req, res, next) => {
        const rel = decodeURIComponent((req.url || "").split("?")[0]).replace(/^\/+/, "");
        const file = resolve(CESIUM_BUILD, rel);
        const top = rel.split("/")[0];
        // Samo poznate mape i bez izlaska iz Build/Cesium (path traversal).
        if (!CESIUM_DIRS.includes(top) || !file.startsWith(CESIUM_BUILD + sep)
            || !existsSync(file) || !statSync(file).isFile()) return next();
        res.setHeader("Content-Type", MIME[extname(file).toLowerCase()] || "application/octet-stream");
        createReadStream(file).pipe(res);
      });
    },
    // Build: kopiraj mape u dist/cesium/ (backend ih poslužuje kao statiku).
    writeBundle() {
      for (const d of CESIUM_DIRS) {
        cpSync(join(CESIUM_BUILD, d), join(outDir, "cesium", d), { recursive: true });
      }
    },
  };
}

export default defineConfig({
  plugins: [cesiumStatic()],
  // Cesium (buildModuleUrl) čita globalnu varijablu CESIUM_BASE_URL.
  define: { CESIUM_BASE_URL: JSON.stringify(CESIUM_BASE_URL) },
  server: {
    port: 5173,
    proxy: {
      "/api": `http://127.0.0.1:${BACKEND_PORT}`,
      "/ws": { target: `ws://127.0.0.1:${BACKEND_PORT}`, ws: true },
    },
  },
  // Cesium je velik (~4-5 MB minificiran) — upozorenje o veličini chunka je očekivano.
  build: { outDir: "dist", emptyOutDir: true, target: "es2020", chunkSizeWarningLimit: 6000 },
});
