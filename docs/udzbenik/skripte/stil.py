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

# boje usklađene s predloškom (predlozak.typ) — paleta knjige „Od vozača do mehaničara"
PETROL = "#0e4f63"
PLAVA = PETROL
SVIJETLO_PLAVA = "#0f7c9c"
ZELENA = "#2c6e49"
NARANCASTA = "#c2570a"
LJUBICASTA = "#5b3a8c"
CRVENA = "#b3261e"
SIVA = "#8d9ca5"
INK = "#16222b"
SUSTAVI = {"GPS": PETROL, "GAL": ZELENA, "GLO": CRVENA, "BDS": NARANCASTA}
NIZ = [PETROL, NARANCASTA, ZELENA, LJUBICASTA, CRVENA, SIVA]

# Barlow (isti font kao oznake u knjizi), iz docs/udzbenik/fontovi
from matplotlib import font_manager  # noqa: E402
for _f in ("Barlow-Regular.ttf", "Barlow-Medium.ttf", "Barlow-SemiBold.ttf", "Barlow-Italic.ttf"):
    _p = os.path.join(UDZBENIK, "fontovi", _f)
    if os.path.isfile(_p):
        font_manager.fontManager.addfont(_p)

plt.rcParams.update({
    "figure.figsize": (6.2, 3.4),
    "figure.dpi": 100,
    "font.size": 9,
    "font.family": ["Barlow", "DejaVu Sans"],
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": "#8d9ca5",
    "xtick.color": "#55656f",
    "ytick.color": "#55656f",
    "axes.titlesize": 9.5,
    "axes.titleweight": "semibold",
    "axes.titlecolor": PETROL,
    "axes.labelsize": 9,
    "axes.grid": True,
    "grid.color": "#e3e9ec",
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
