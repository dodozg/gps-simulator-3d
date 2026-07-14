#!/usr/bin/env bash
# Web kontrolni centar + GPS učilište (macOS / Linux). Ekvivalent run_webapp.bat.
# Pokreće FastAPI backend (uvicorn) i otvara preglednik. Frontend se poslužuje
# iz lokalnog builda (pokreni ./build_web.sh prije prvog pokretanja).
set -euo pipefail
cd "$(dirname "$0")"

BUILD="${GPSWEB_BUILD:-$HOME/.local/share/gpsweb}"
export GPSWEB_DIST="$BUILD/dist"

# Preferiraj venv python, fallback na sistemski.
PY="$(pwd)/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

if ! "$PY" -c "import fastapi" >/dev/null 2>&1; then
  echo "[!] fastapi nije dostupan u '$PY'. Pokreni ./setup.sh (ili: pip install -r requirements-web.txt)."
  exit 1
fi

if [ ! -f "$GPSWEB_DIST/index.html" ]; then
  echo "[!] Frontend nije buildan — pokreni ./build_web.sh prvo."
  echo "    (Backend će svejedno raditi na /api, ali bez sučelja.)"
fi

PORT="${GPSWEB_PORT:-8010}"
URL="http://127.0.0.1:$PORT"
echo "[i] Otvaram $URL"
if command -v open >/dev/null 2>&1; then
  open "$URL" || true            # macOS
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" || true        # Linux
fi

exec "$PY" -m uvicorn web.backend.app:app --host 127.0.0.1 --port "$PORT"
