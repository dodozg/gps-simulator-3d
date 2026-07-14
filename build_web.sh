#!/usr/bin/env bash
# Build web frontenda (CesiumJS + TS) na macOS / Linux.
# Ekvivalent build_web.bat. Izvor se kopira u lokalni dir i tamo builda
# (kao na Windowsu; drži node_modules izvan Google Drivea i općenito čisto).
# Traži Node.js 18+.
set -euo pipefail
cd "$(dirname "$0")"

SRC="$(pwd)/web/frontend"
BUILD="${GPSWEB_BUILD:-$HOME/.local/share/gpsweb}"

if ! command -v node >/dev/null 2>&1; then
  echo "[!] Node.js nije pronađen. Instaliraj Node 18+ (npr. 'brew install node') i pokreni ponovno."
  exit 1
fi

echo "[i] Node $(node --version), build dir: $BUILD"
mkdir -p "$BUILD"
cp "$SRC/package.json" "$SRC/vite.config.ts" "$SRC/tsconfig.json" "$SRC/index.html" "$BUILD/"
rm -rf "$BUILD/src"
cp -R "$SRC/src" "$BUILD/src"

cd "$BUILD"
if [ ! -d node_modules ]; then
  echo "[i] npm install (prvi put, može potrajati)..."
  npm install
fi
echo "[i] npm run build..."
npm run build

if [ -f "$BUILD/dist/index.html" ]; then
  echo "[OK] Frontend buildan: $BUILD/dist"
  echo "     Sada pokreni ./run_webapp.sh"
else
  echo "[!] Build nije uspio — provjeri poruke iznad."
  exit 1
fi
