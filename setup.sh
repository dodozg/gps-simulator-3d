#!/usr/bin/env bash
# Kreira Python venv i instalira ovisnosti (macOS / Linux).
# Ekvivalent setup.bat. Napomena: .venv je po stroju — na dijeljenom Google
# Driveu Windows i Mac venv se ne mogu dijeliti (recreate po stroju).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
echo "[i] Kreiram .venv ($("$PY" --version))..."
"$PY" -m venv .venv --clear
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip >/dev/null
echo "[i] Instaliram ovisnosti (engine + viz + dev + web)..."
pip install -r requirements-viz.txt -r requirements-dev.txt -r requirements-web.txt

echo "[OK] Gotovo. Aktiviraj s: source .venv/bin/activate"
echo "     Web: ./build_web.sh pa ./run_webapp.sh"
echo "     Alati: ./gps.sh benchmark | skyplot | rtk | spoofing | iono | multignss | scenario"
