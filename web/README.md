# Web kontrolni centar + GPS učilište

Moderno web sučelje za GPS_Simulator_3D: 3D globus (CesiumJS, Google-Earth
osjećaj), živa simulacija, telemetrija i — kroz cijelo sučelje — **edukativni
sloj** (pojmovnik na klik, dvojezično HR/EN, Početnik/Stručnjak). Backend
(FastAPI) koristi postojeći numpy engine **izravno**, bez duplikacije fizike.

## Arhitektura

- `backend/` — FastAPI adapter oko enginea: `/ws/sim` (živa simulacija preko
  WebSocketa), `/api/rtk|spoofing|multignss|iono|scenario` (eksperimenti),
  `/api/glossary|lessons` (učilište), `/api/constellation` (orbite).
- `frontend/` — Vite + TypeScript + CesiumJS. Globus, paneli, pojmovnik.
- `content/` — `glossary.{hr,en}.json`, `lessons.{hr,en}.json` (proširiv sadržaj).

## Pokretanje (Windows)

Zbog Google Drive/NTFS ograničenja `node_modules` i build **ne mogu** biti na
G: disku, pa se frontend builda u lokalni dir (`%LOCALAPPDATA%\gpsweb`).

1. **`build_web.bat`** — kopira frontend izvor lokalno, `npm install` + `npm run
   build` (traži Node 18+). Pokreni jednom (i nakon promjena frontenda).
2. **`run_webapp.bat`** — pokreće FastAPI (uvicorn) i otvara
   `http://127.0.0.1:8000`. Backend poslužuje buildani frontend.

Backend ovisnosti: `pip install -r requirements-web.txt` (u `.venv`).

## Razvoj (opcionalno)

U lokalnom build diru: `npm run dev` diže Vite dev-server (HMR) na `:5173` koji
proxira `/api` i `/ws` na backend (`uvicorn web.backend.app:app --reload`).

## CesiumJS imagery

Bez tokena koristi se OpenStreetMap imagery + elipsoidni teren (radi odmah).
Za satelitsku sliku i pravi teren postavi besplatni Cesium ion token u
`web/frontend/.env`: `VITE_CESIUM_ION_TOKEN=...` pa ponovno buildaj.

## Status

Faza 1 (MVP): globus, dvoklik-rover, sateliti/orbite/zrake, telemetrija +
RAIM banner, play/pause/brzina, doba dana, pojmovnik, HR/EN, Početnik/Stručnjak.
Sljedeće (Faza 2/3): paneli eksperimenata s grafovima, live skyplot, scenario
manager, vođene lekcije.
