#!/usr/bin/env bash
# Jedinstveni launcher za GPS_Simulator_3D alate (macOS / Linux).
# Ekvivalent pojedinačnih run_*.bat datoteka na Windowsu.
#
# Uporaba:
#   ./gps.sh benchmark [args]     # headless: greška / NIS / RAIM
#   ./gps.sh skyplot [args]       # skyplot + GDOP/greška/NIS grafovi (PNG)
#   ./gps.sh rtk [args]           # carrier-phase RTK demo
#   ./gps.sh spoofing [args]      # spoofing/jamming lab
#   ./gps.sh iono [args]          # Klobuchar dnevna ionosfera
#   ./gps.sh multignss [args]     # GPS+GAL+GLO+BDS dostupnost/PDOP/ISB
#   ./gps.sh scenario [args]      # snimanje/reprodukcija scenarija (JSON)
#   ./gps.sh tests [args]         # pytest
#   ./gps.sh web                  # build (ako treba) + pokreni web centar
set -euo pipefail
cd "$(dirname "$0")"

# Preferiraj venv python, fallback na sistemski + PYTHONPATH na venv pakete.
PY="$(pwd)/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
  if [ -d "$(pwd)/.venv/lib" ]; then
    SP="$(ls -d "$(pwd)"/.venv/lib/python*/site-packages 2>/dev/null | head -n1 || true)"
    [ -n "${SP:-}" ] && export PYTHONPATH="${SP}${PYTHONPATH:+:$PYTHONPATH}"
  fi
fi

cmd="${1:-}"
[ $# -gt 0 ] && shift || true

case "$cmd" in
  benchmark|bench) exec "$PY" benchmark.py "$@" ;;
  skyplot)        exec "$PY" skyplot.py "$@" ;;
  rtk)            exec "$PY" rtk.py "$@" ;;
  spoofing|spoof) exec "$PY" spoofing.py "$@" ;;
  iono)           exec "$PY" iono.py "$@" ;;
  multignss|multi) exec "$PY" multignss.py "$@" ;;
  scenario)       exec "$PY" scenario.py "$@" ;;
  tests|test|pytest) exec "$PY" -m pytest "$@" ;;
  web)            [ -f "${GPSWEB_BUILD:-$HOME/.local/share/gpsweb}/dist/index.html" ] || ./build_web.sh
                  exec ./run_webapp.sh ;;
  ""|-h|--help|help)
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 0 ;;
  *)
    echo "[!] Nepoznata naredba: $cmd"
    echo "    Pokreni './gps.sh help' za popis."
    exit 1 ;;
esac
