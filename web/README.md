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

## Pokretanje

Frontend se builda u **lokalni dir** izvan repozitorija (na Windowsu i zbog
Google Drive/NTFS ograničenja — `node_modules` na G: puca): Windows
`%LOCALAPPDATA%\gpsweb`, macOS/Linux `~/.local/share/gpsweb` (promjenjivo preko
`GPSWEB_BUILD`). Traži Node 18+.

**Windows**
1. **`build_web.bat`** — kopira frontend izvor lokalno, `npm install` + `npm run
   build`. Pokreni jednom (i nakon promjena frontenda).
2. **`run_webapp.bat`** — pokreće FastAPI (uvicorn) i otvara
   `http://127.0.0.1:8010`. Backend poslužuje buildani frontend.

**macOS / Linux**
1. **`./build_web.sh`** — isto (kopira izvor u `$GPSWEB_BUILD`, `npm install` +
   `npm run build`).
2. **`./run_webapp.sh`** — postavi `GPSWEB_DIST`, digne uvicorn, otvori
   preglednik (`open`/`xdg-open`). Kraće: **`./gps.sh web`** (buildati ako treba,
   pa pokrenuti).

Backend ovisnosti: `pip install -r requirements-web.txt` (u `.venv`;
`setup.bat`/`./setup.sh` to već rade).

**Port:** backend sluša na **8010** (port 8000 zauzima druga lokalna app). Za
promjenu postavi `GPSWEB_PORT` prije pokretanja (npr. `set GPSWEB_PORT=8080` na
Windowsu ili `GPSWEB_PORT=8080 ./run_webapp.sh` na macOS/Linux); dev-server
proxy (`vite.config.ts`) čita isti env.

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
