"""Zajednički stil grafova udžbenika + putanje.

Svaka skripta `slike_NN.py` generira slike poglavlja NN iz STVARNOG koda simulatora
(engine se uvozi iz korijena repozitorija), sa fiksnim sjemenom — brojke u knjizi su
reproducibilne: `python docs/udzbenik/build.py --slike`.
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OVDJE = os.path.dirname(os.path.abspath(__file__))
UDZBENIK = os.path.dirname(OVDJE)
REPO = os.path.dirname(os.path.dirname(UDZBENIK))
SLIKE = os.path.join(UDZBENIK, "slike")
os.makedirs(SLIKE, exist_ok=True)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# boje usklađene s predloskom (predlozak.typ)
PLAVA = "#1f4e79"
SVIJETLO_PLAVA = "#1565c0"
ZELENA = "#2e7d32"
NARANCASTA = "#ef6c00"
LJUBICASTA = "#8e24aa"
CRVENA = "#c62828"
SIVA = "#757575"
SUSTAVI = {"GPS": "#1565c0", "GAL": "#2e7d32", "GLO": "#c62828", "BDS": "#ef6c00"}
NIZ = [PLAVA, NARANCASTA, ZELENA, LJUBICASTA, CRVENA, SIVA]

plt.rcParams.update({
    "figure.figsize": (6.2, 3.4),
    "figure.dpi": 100,
    "font.size": 9,
    "font.family": "DejaVu Sans",
    "axes.titlesize": 9.5,
    "axes.labelsize": 9,
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.prop_cycle": matplotlib.cycler(color=NIZ),
    "legend.fontsize": 8,
    "legend.frameon": False,
    "lines.linewidth": 1.4,
    "svg.fonttype": "path",
    "axes.formatter.use_locale": False,
})


def decimalni_zarez(ax):
    """Hrvatski zapis brojeva na osima (zarez umjesto točke)."""
    from matplotlib.ticker import FuncFormatter

    def f(x, _pos):
        s = f"{x:g}"
        return s.replace(".", ",").replace("-", "−")
    ax.xaxis.set_major_formatter(FuncFormatter(f))
    ax.yaxis.set_major_formatter(FuncFormatter(f))


def spremi(fig, ime):
    """Spremi kao SVG u docs/udzbenik/slike/<ime>.svg."""
    put = os.path.join(SLIKE, ime + ".svg")
    fig.tight_layout()
    fig.savefig(put, format="svg", bbox_inches="tight")
    plt.close(fig)
    print("  slika:", os.path.relpath(put, UDZBENIK))
    return put


# --- rezultati sandbox studija (docs/udzbenik/studije/rezultati/<ime>/results.json) ---------------
def ucitaj_studiju(ime):
    import json
    p = os.path.join(UDZBENIK, "studije", "rezultati", ime, "results.json")
    if not os.path.isfile(p):
        print(f"  (studija {ime} još nije odvrćena: python docs/udzbenik/skripte/studije.py {ime})")
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def agregat(res, metrike, param=None, filtar=None, estimator=None):
    """(x, mean, 95 % CI) po točki sweepa. `filtar(params)` bira podskup (npr. jedan skup sustava)."""
    out = []
    for red in res["aggregate"]:
        if estimator and red.get("estimator") != estimator:
            continue
        if filtar and not filtar(red["params"]):
            continue
        st = {"x": red["params"].get(param) if param else red.get("location"),
              "params": red["params"], "location": red.get("location"), "estimator": red.get("estimator")}
        for k in metrike:
            a = red["metrics"][k]
            st[k] = {"mean": a["mean"], "median": a["median"], "ci": [a["ci_lo"], a["ci_hi"]], "n": a["n"]}
        out.append(st)
    if param:
        out.sort(key=lambda s: (s["x"] is None, s["x"]))
    return out
