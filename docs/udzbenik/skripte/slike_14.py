"""Poglavlje 14 — tablica rezultata primjera plugina (obični LS vs WLS vs EKF)."""
import json
import os

from stil import UDZBENIK, agregat, ucitaj_studiju


def main():
    r = ucitaj_studiju("ls_vs_wls")
    b = {}
    if r is not None:
        met = ("h_err_median", "h_err_p95", "h_err_p99", "v_err_p95")
        for st in agregat(r, met, "attack.bias_m"):
            b.setdefault(str(st["x"]), {})[st["estimator"]] = {m: {"mean": round(st[m]["mean"], 2),
                                                                  "pm": round((st[m]["ci"][1] - st[m]["ci"][0]) / 2, 2)} for m in met}
    with open(os.path.join(UDZBENIK, "skripte", "brojke_14.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
