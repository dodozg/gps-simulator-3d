"""Primjer plugina za istraživački sandbox (udžbenik, pogl. 14).

Registrira:
  * procjenitelj ``ls_obicni`` — snapshot Gauss-Newton BEZ težina i BEZ RAIM-a
    (jedan sat po sustavu, isti model kao prijemnik: ρ = |s − x| + Sagnac + b_sustav);
  * metriku ``h_err_p99`` — 99. percentil horizontalne pogreške nakon zagrijavanja.

Upotreba (iz korijena repozitorija):
    python sandbox.py run docs/udzbenik/primjeri/ls_vs_wls.json --workers 4
"""
import numpy as np

from physics_engine import calculate_sagnac_correction
from sandbox import register_estimator, register_metric


@register_estimator("ls_obicni", "snapshot LS bez težina i bez RAIM-a (primjer iz udžbenika)")
class ObicniLS:
    def __init__(self, world):
        self.x = None

    def estimate(self):
        """Procjena koju sandbox koristi za odabir satelita (None prije prvog fixa)."""
        return None if self.x is None else self.x[:3].copy()

    def solve(self, signals, t):
        sustavi = sorted({s.get("system", "GPS") for s in signals})
        m = 3 + len(sustavi)
        if len(signals) < m:
            return None, {"status": "unavailable", "n_used": len(signals)}
        stup = {s: 3 + k for k, s in enumerate(sustavi)}
        x = np.zeros(m)
        if self.x is not None and len(self.x) >= 3:
            x[:3] = self.x[:3]
        for _ in range(10):
            G = np.zeros((len(signals), m))
            y = np.zeros(len(signals))
            for i, s in enumerate(signals):
                d = x[:3] - s["broadcast_pos"]
                r = np.linalg.norm(d)
                c = stup[s.get("system", "GPS")]
                y[i] = s["pseudorange"] - (r + x[c] + calculate_sagnac_correction(s["broadcast_pos"], x[:3]))
                G[i, :3] = d / r
                G[i, c] = 1.0
            dx = np.linalg.lstsq(G, y, rcond=None)[0]
            x = x + dx
            if np.linalg.norm(dx[:3]) < 1e-3:
                break
        self.x = x
        Q = np.linalg.inv(G.T @ G)
        return x[:3].copy(), {"status": "disabled", "alarm": False, "excluded": [],
                              "gdop": float(np.sqrt(np.trace(Q))), "n_used": len(signals)}


@register_metric("h_err_p99", "horizontalna pogreška [m], p99 (nakon warmup_s)", unit="m")
def h_err_p99(tr):
    w = tr["fix"] & (tr["t"] >= tr["meta"]["warmup_s"])
    return float(np.percentile(tr["err_h"][w], 99)) if w.any() else float("nan")
