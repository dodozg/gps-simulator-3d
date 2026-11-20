"""Izradi PDF udžbenika.

    python docs/udzbenik/build.py            # samo PDF (koristi postojeće slike)
    python docs/udzbenik/build.py --slike    # najprije ponovno izračunaj sve slike iz simulatora
    python docs/udzbenik/build.py --slike 06 # samo slike poglavlja 06, pa PDF

Treba: `pip install typst matplotlib` (+ ovisnosti simulatora iz requirements.txt).
"""
import argparse
import glob
import os
import re
import runpy
import sys
import time

OVDJE = os.path.dirname(os.path.abspath(__file__))
IZLAZ = os.path.join(OVDJE, "Satelitska_navigacija_u_simulatoru.pdf")


def slike(filtar=None):
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    sys.path.insert(0, os.path.join(OVDJE, "skripte"))
    for skripta in sorted(glob.glob(os.path.join(OVDJE, "skripte", "slike_*.py"))):
        oznaka = os.path.basename(skripta)[6:-3]
        if filtar and not oznaka.startswith(filtar):
            continue
        t = time.time()
        print(f"[slike {oznaka}]")
        runpy.run_path(skripta, run_name="__main__")
        print(f"  ({time.time() - t:.1f} s)")


DECIMALNI = re.compile(r"(\d),(\d)")


def popravi_decimalni_zarez():
    """U Typst formulama je zarez razdjelnik i dobiva razmak („2,5" se slaže kao „2, 5").
    Hrvatski decimalni zarez se zato u formuli piše 2","5 — ovdje automatski: unutar $...$
    (izvan ``` blokova) svaki znamenka,znamenka postaje znamenka","znamenka. Popravlja na mjestu."""
    for put in glob.glob(os.path.join(OVDJE, "**", "*.typ"), recursive=True):
        izvor = open(put, encoding="utf-8").read()
        dijelovi = izvor.split("```")
        for k in range(0, len(dijelovi), 2):            # parni dijelovi su izvan raw blokova
            seg = re.split("(?<!" + re.escape(chr(92)) + ")[$]", dijelovi[k])   # $ koji nije escapean
            for j in range(1, len(seg), 2):             # neparni su unutar $...$
                seg[j] = DECIMALNI.sub(lambda m: m.group(1) + '","' + m.group(2), seg[j])
            dijelovi[k] = "$".join(seg)
        novo = "```".join(dijelovi)
        for k in range(0, len(dijelovi), 2):
            for red in dijelovi[k].splitlines():
                if "~" in red and not red.lstrip().startswith("//"):
                    print("  UPOZORENJE (~ je u Typstu tvrdi razmak, piši 'oko' ili ≈):",
                          os.path.relpath(put, OVDJE), "|", red.strip()[:70])
        if novo != izvor:
            open(put, "w", encoding="utf-8", newline="").write(novo)
            print("  decimalni zarez popravljen:", os.path.relpath(put, OVDJE))


def pdf():
    popravi_decimalni_zarez()
    import typst
    t = time.time()
    try:
        typst.compile(os.path.join(OVDJE, "udzbenik.typ"), output=IZLAZ, root=OVDJE)
    except typst.TypstError as e:
        print(getattr(e, "diagnostic", e))
        raise SystemExit(1)
    print(f"PDF: {IZLAZ} ({os.path.getsize(IZLAZ) / 1e6:.1f} MB, {time.time() - t:.1f} s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slike", nargs="?", const="", default=None, metavar="POGLAVLJE",
                    help="ponovno izračunaj slike (opcionalno samo za zadano poglavlje)")
    a = ap.parse_args()
    if a.slike is not None:
        slike(a.slike or None)
    pdf()


if __name__ == "__main__":
    sys.exit(main())
