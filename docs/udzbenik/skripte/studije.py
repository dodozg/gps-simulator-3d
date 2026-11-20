"""Odvrti sandbox studije koje knjiga citira i spremi rezultate u docs/udzbenik/studije/rezultati/.

    python docs/udzbenik/skripte/studije.py              # sve (traje desetak minuta i više)
    python docs/udzbenik/skripte/studije.py maska raim_roc

Studije su vlastite (docs/udzbenik/studije/*.json) i ugrađeni primjeri (sandbox/examples/).
Rezultati su deterministički (isto sjeme -> isti brojevi) i ne ovise o broju procesa.
"""
import os
import subprocess
import sys
import time

OVDJE = os.path.dirname(os.path.abspath(__file__))
UDZBENIK = os.path.dirname(OVDJE)
REPO = os.path.dirname(os.path.dirname(UDZBENIK))
REZ = os.path.join(UDZBENIK, "studije", "rezultati")

STUDIJE = {
    "max_sats": os.path.join(UDZBENIK, "studije", "max_sats.json"),
    "maska": os.path.join(UDZBENIK, "studije", "maska.json"),
    "ekf_vs_wls": os.path.join(REPO, "sandbox", "examples", "ekf_vs_wls.json"),
    "multignss_mask": os.path.join(REPO, "sandbox", "examples", "multignss_mask.json"),
    "raim_roc": os.path.join(REPO, "sandbox", "examples", "raim_roc.json"),
    "spoof_offset": os.path.join(REPO, "sandbox", "examples", "spoof_offset.json"),
    "jamming_jn": os.path.join(REPO, "sandbox", "examples", "jamming_jn.json"),
    "ls_vs_wls": os.path.join(UDZBENIK, "primjeri", "ls_vs_wls.json"),
}


def main(imena):
    radnika = max(1, min(6, (os.cpu_count() or 2) - 1))
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8")
    for ime in imena or STUDIJE:
        t = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {ime} ...", flush=True)
        out = os.path.join(REZ, ime)
        r = subprocess.run([sys.executable, os.path.join(REPO, "sandbox.py"), "run", STUDIJE[ime],
                            "--workers", str(radnika), "--out", out], cwd=REPO, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            print(r.stdout[-2000:], r.stderr[-3000:])
            raise SystemExit(f"{ime}: neuspjeh")
        print(f"    gotovo za {time.time() - t:.0f} s -> {os.path.relpath(out, UDZBENIK)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
