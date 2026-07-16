"""Meta podaci: parametri konstelacije (za crtanje orbita) + edukativni sadržaj."""
import json
import os

import numpy as np
from fastapi import APIRouter, HTTPException

from satellite import WalkerDeltaConstellation, GNSS_SYSTEMS
from physics_engine import R_EARTH

router = APIRouter()

OMEGA_E = 7.2921159e-5
CONTENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")


@router.get("/constellation")
def api_constellation():
    con = WalkerDeltaConstellation(rng=np.random.default_rng(0))
    lans = sorted({round(s.lan, 3) for s in con.satellites})
    return {
        "omega_e": OMEGA_E,
        "r_earth": R_EARTH,
        "gps": {"a": con.a, "e": con.e, "i": con.i, "w": con.w,
                "planes": lans, "n_sats": len(con.satellites)},
        "systems": {k: {"alt": v["alt"], "inc": v["inc"], "isb_m": v["isb_m"],
                        "planes": v["p"], "sats": v["t"]}
                    for k, v in GNSS_SYSTEMS.items()},
    }


def _load_content(kind, lang):
    lang = lang if lang in ("hr", "en") else "hr"
    path = os.path.join(CONTENT_DIR, f"{kind}.{lang}.json")
    if not os.path.isfile(path):
        raise HTTPException(404, f"Sadržaj ne postoji: {kind}.{lang}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/glossary")
def api_glossary(lang: str = "hr"):
    return _load_content("glossary", lang)


@router.get("/lessons")
def api_lessons(lang: str = "hr"):
    return _load_content("lessons", lang)


@router.get("/guide")
def api_guide(lang: str = "hr"):
    """Dugoformni edukativni vodič ("GPS objašnjen") kao Markdown tekst.

    Vraća {"md", "lang"}. Ako prijevod za traženi jezik ne postoji, pada natrag na
    hrvatski (izvorni) uz `lang` koji odražava STVARNO posluženi jezik, pa UI može
    prikazati napomenu. Sadržaj je autorski (povjerljiv) pa ga frontend renderira
    minimalnim Markdown prikazom.
    """
    lang = lang if lang in ("hr", "en") else "hr"
    path = os.path.join(CONTENT_DIR, f"guide.{lang}.md")
    if not os.path.isfile(path):
        lang, path = "hr", os.path.join(CONTENT_DIR, "guide.hr.md")
    if not os.path.isfile(path):
        raise HTTPException(404, "Vodič ne postoji")
    with open(path, "r", encoding="utf-8") as f:
        return {"md": f.read(), "lang": lang}
