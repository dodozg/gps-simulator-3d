"""Konceptualne skice (nisu rezultati simulacije, osim LAMBDA primjera koji koristi rtk.lambda_ils):
koordinatni sustavi i širine (pogl. 2), trokut za kosu udaljenost (pogl. 1),
geometrija dvostrukih razlika (pogl. 11) i LAMBDA dekorelacija u 2D (pogl. 11)."""
import json
import os

import numpy as np
from matplotlib.patches import Arc, Ellipse, FancyArrowPatch

from stil import INK, NARANCASTA, PETROL, SIVA, UDZBENIK, ZELENA, plt, spremi

import rtk


def strelica(ax, a, b, boja=PETROL, lw=1.2, stil="-|>", ms=9):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=stil, mutation_scale=ms, color=boja, lw=lw, shrinkA=0, shrinkB=0))


def tekst(ax, xy, s, boja=INK, **kw):
    ax.text(*xy, s, color=boja, fontsize=kw.pop("fs", 9), **kw)


def prazno(ax):
    ax.set_aspect("equal")
    ax.axis("off")


def koordinate():
    """Meridijanski presjek: spljošteni elipsoid, geodetska i geocentrična širina, lokalni ENU."""
    fig, ax = plt.subplots(figsize=(5.6, 4.1))
    prazno(ax)
    a, b = 1.0, 0.78                      # spljoštenost pretjerana radi vidljivosti
    t = np.linspace(0, 2 * np.pi, 400)
    ax.plot(a * np.cos(t), b * np.sin(t), color=PETROL, lw=1.4)
    ax.plot([-1.25, 1.35], [0, 0], color=SIVA, lw=0.7)
    ax.plot([0, 0], [-0.95, 1.1], color=SIVA, lw=0.7)
    tekst(ax, (1.36, -0.07), "ekvator", SIVA, fs=8)
    tekst(ax, (0.03, 1.08), "z (os rotacije)", SIVA, fs=8)
    phi = np.radians(45)                  # geodetska širina točke P
    # točka na elipsi s normalom pod kutom phi: parametarski preko reducirane širine
    beta = np.arctan(b / a * np.tan(phi))
    P = np.array([a * np.cos(beta), b * np.sin(beta)])
    n = np.array([np.cos(phi), np.sin(phi)])
    # normala siječe ekvatorsku os u točki Q (ne u središtu!)
    Qx = P[0] - P[1] / n[1] * n[0]
    ax.plot([Qx, P[0] + 0.35 * n[0]], [0, P[1] + 0.35 * n[1]], color=NARANCASTA, lw=1.2)
    ax.plot([0, P[0]], [0, P[1]], color=PETROL, lw=1.0, ls="--")
    ax.add_patch(Arc((Qx, 0), 0.9, 0.9, theta1=0, theta2=45, color=NARANCASTA, lw=1.1))
    tekst(ax, (Qx + 0.47, 0.13), "φ", NARANCASTA, fs=11)
    phi_c = np.degrees(np.arctan2(P[1], P[0]))
    ax.add_patch(Arc((0, 0), 0.36, 0.36, theta1=0, theta2=phi_c, color=PETROL, lw=1.0))
    tekst(ax, (0.2, 0.05), "φ′", PETROL, fs=11)
    tekst(ax, (-1.25, -1.02), "φ  geodetska širina: kut normale na elipsoid", NARANCASTA, fs=8)
    tekst(ax, (-1.25, -1.14), "φ′ geocentrična širina: kut spojnice sa središtem", PETROL, fs=8)
    ax.plot(*P, "o", color=INK, ms=4)
    tekst(ax, (P[0] - 0.13, P[1] + 0.05), "P", INK, fs=10, fontweight="bold")
    # lokalni sustav: gore = normala, sjever = tangenta prema polu
    up = n
    north = np.array([-np.sin(phi), np.cos(phi)])
    strelica(ax, P, P + 0.42 * up, ZELENA)
    strelica(ax, P, P + 0.42 * north, ZELENA)
    tekst(ax, P + 0.45 * up + np.array([0.02, 0]), "gore (U)", ZELENA, fs=8.5)
    tekst(ax, P + 0.45 * north + np.array([-0.18, 0.03]), "sjever (N)", ZELENA, fs=8.5)
    tekst(ax, (P[0] + 0.07, P[1] - 0.12), "istok (E) iz ravnine", ZELENA, fs=8)
    tekst(ax, (0.45, -0.95), "elipsoid WGS-84 (spljoštenost pretjerana)", SIVA, fs=7.5)
    ax.set_xlim(-1.3, 1.75)
    ax.set_ylim(-1.2, 1.25)
    spremi(fig, "skica-koordinate")


def trokut():
    """Središte Zemlje O, prijemnik P, satelit S: elevacija i kosinusov poučak."""
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    prazno(ax)
    R, rs = 1.0, 2.15
    t = np.linspace(np.radians(20), np.radians(160), 200)
    ax.plot(R * np.cos(t), R * np.sin(t) - 1.0, color=PETROL, lw=1.4)
    O = np.array([0.0, -1.0])
    P = O + R * np.array([np.cos(np.radians(105)), np.sin(np.radians(105))])
    up = (P - O) / R
    el = np.radians(32)
    hor = np.array([up[1], -up[0]])        # horizont (desno)
    smjer = np.cos(el) * hor + np.sin(el) * up
    # S na kružnici polumjera rs oko O, u smjeru `smjer` od P
    bq = 2 * P @ smjer - 2 * O @ smjer
    cq = (P - O) @ (P - O) - rs ** 2
    d = (-bq + np.sqrt(bq * bq - 4 * cq)) / 2
    S = P + d * smjer
    ax.plot([O[0], P[0]], [O[1], P[1]], color=SIVA, lw=1.0)
    ax.plot([O[0], S[0]], [O[1], S[1]], color=SIVA, lw=1.0, ls="--")
    ax.plot([P[0], S[0]], [P[1], S[1]], color=NARANCASTA, lw=1.6)
    ax.plot([P[0] - 0.55 * hor[0], P[0] + 1.1 * hor[0]], [P[1] - 0.55 * hor[1], P[1] + 1.1 * hor[1]], color=SIVA, lw=0.7, ls=":")
    ax.add_patch(Arc(tuple(P), 0.6, 0.6, theta1=np.degrees(np.arctan2(hor[1], hor[0])),
                     theta2=np.degrees(np.arctan2(smjer[1], smjer[0])), color=NARANCASTA, lw=1.1))
    for tocka, ime, pomak in ((O, "O (središte)", (0.05, -0.08)), (P, "P (prijemnik)", (-0.55, 0.05)), (S, "S (satelit)", (0.06, 0.04))):
        ax.plot(*tocka, "o", color=INK, ms=4)
        tekst(ax, tocka + np.array(pomak), ime, INK, fs=8.5)
    tekst(ax, (O + P) / 2 + np.array([0.05, -0.05]), "R", SIVA, fs=9)
    tekst(ax, (O + S) / 2 + np.array([0.06, -0.12]), r"$r_s = R + h$", SIVA, fs=9)
    tekst(ax, (P + S) / 2 + np.array([-0.12, 0.08]), "d (kosa udaljenost)", NARANCASTA, fs=9)
    tekst(ax, P + 0.33 * (hor + smjer) / 2 + np.array([0.02, -0.03]), "el", NARANCASTA, fs=9)
    tekst(ax, (P[0] + 0.25, P[1] - 0.32), "horizont", SIVA, fs=8)
    ax.set_xlim(-1.1, S[0] + 0.75)
    ax.set_ylim(-1.15, S[1] + 0.25)
    spremi(fig, "skica-trokut")


def dvostruke():
    """Baza B i rover R, sateliti i (referentni) i j: jednostruke i dvostruke razlike."""
    fig, ax = plt.subplots(figsize=(6.2, 3.5))
    prazno(ax)
    Si, Sj = np.array([1.2, 3.0]), np.array([4.6, 2.7])
    B, Rv = np.array([1.6, 0.0]), np.array([3.6, 0.15])
    ax.plot([0.4, 5.4], [-0.08, 0.02], color=SIVA, lw=0.8)
    for S, ime in ((Si, "satelit i (referentni)"), (Sj, "satelit j")):
        ax.plot(*S, "s", color=PETROL, ms=7)
        tekst(ax, S + np.array([-0.4, 0.17]), ime, PETROL, fs=8.5)
    for P, ime in ((B, "baza B (poznat položaj)"), (Rv, "rover R")):
        ax.plot(*P, "^", color=NARANCASTA, ms=8)
        tekst(ax, P + np.array([-0.55, -0.32]), ime, NARANCASTA, fs=8.5)
    for S in (Si, Sj):
        for P, ls in ((B, "--"), (Rv, "-")):
            ax.plot([S[0], P[0]], [S[1], P[1]], color=SIVA if ls == "--" else PETROL, lw=1.0, ls=ls)
    strelica(ax, B + np.array([0, -0.55]), Rv + np.array([0, -0.55]), ZELENA, lw=1.2, stil="<|-|>")
    tekst(ax, (2.2, -0.82), "baza (bazna linija)", ZELENA, fs=8.5)
    tekst(ax, (5.25, 2.05), "jednostruka razlika R − B:\nponištava sat satelita i\n(za kratku bazu) atmosferu", INK, fs=7.8)
    tekst(ax, (5.25, 1.05), "dvostruka razlika j − i:\nponištava i satove prijemnika;\nostaju geometrija, λ∇ΔN, šum", INK, fs=7.8)
    ax.set_xlim(0.2, 7.6)
    ax.set_ylim(-1.0, 3.5)
    spremi(fig, "skica-dvostruke")


def lambda_2d():
    """Float neodređenosti s jako koreliranom kovarijancom: zaokruživanje vs. LAMBDA (ILS)."""
    sig1, sig2, rho = 0.55, 0.62, 0.985
    Q = np.array([[sig1 ** 2, rho * sig1 * sig2], [rho * sig1 * sig2, sig2 ** 2]])
    # float vektor (iz rešetke razlomljenih dijelova) za koji zaokruživanje NAJVIŠE promaši ILS rješenje
    Qi0 = np.linalg.inv(Q)
    najbolji = None
    for fx in np.arange(0.05, 1.0, 0.05):
        for fy in np.arange(0.05, 1.0, 0.05):
            a_ = np.array([2.0 + fx, -1.0 + fy])
            c_, n_, _ = rtk.lambda_ils(a_, Q, m=2)
            if np.all(np.round(a_) == c_[0]) or abs(fx - 0.5) < 0.06 or abs(fy - 0.5) < 0.06:
                continue
            if n_[1] / n_[0] < 2.0:          # jasan pobjednik (kao ratio test u simulatoru)
                continue
            visak = float((a_ - np.round(a_)) @ Qi0 @ (a_ - np.round(a_))) - float(n_[0])
            if najbolji is None or visak > najbolji[0]:
                najbolji = (visak, a_)
    a = np.round(najbolji[1], 2)
    cands, norme, p_boot = rtk.lambda_ils(a, Q, m=2)
    ils = cands[0]
    okr = np.round(a)
    Qi = np.linalg.inv(Q)
    d_okr = float((a - okr) @ Qi @ (a - okr))
    # 2D cjelobrojna dekorelacija (jedan korak Gaussove redukcije) samo za crtanje
    mu = np.round(Q[0, 1] / Q[0, 0])
    Z = np.array([[1.0, 0.0], [-mu, 1.0]])            # z2' = z2 − mu·z1
    Qz = Z @ Q @ Z.T
    az = Z @ a

    def elipsa(ax, c, C, boja):
        w, v = np.linalg.eigh(C)
        kut = np.degrees(np.arctan2(v[1, 1], v[0, 1]))
        for k, alfa in ((1, 0.25), (2, 0.12)):
            ax.add_patch(Ellipse(c, 2 * k * np.sqrt(w[1]), 2 * k * np.sqrt(w[0]), angle=kut, color=boja, alpha=alfa, lw=0))

    fig, axs = plt.subplots(1, 2, figsize=(6.6, 3.2))
    for ax, c, C, naslov, oznake in ((axs[0], a, Q, "izvorni prostor (jako korelirano)", True),
                                     (axs[1], az, Qz, "nakon Z-transformacije (dekorelirano)", False)):
        elipsa(ax, c, C, PETROL)
        g = np.arange(np.floor(c[0]) - 3, np.ceil(c[0]) + 4)
        h = np.arange(np.floor(c[1]) - 3, np.ceil(c[1]) + 4)
        X, Y = np.meshgrid(g, h)
        ax.plot(X, Y, ".", color=SIVA, ms=3)
        ax.plot(*c, "x", color=INK, ms=7, mew=1.5)
        if oznake:
            ax.plot(*okr, "o", mfc="none", mec=NARANCASTA, ms=9, mew=1.5, label="zaokruživanje")
            ax.plot(*ils, "o", color=ZELENA, ms=6, label="LAMBDA (ILS)")
            ax.legend(loc="upper left", fontsize=7.5)
        else:
            ax.plot(*(Z @ ils), "o", color=ZELENA, ms=6)
        ax.set_title(naslov, fontsize=8.5)
        ax.set_aspect("equal")
        ax.set_xlim(c[0] - 2.6, c[0] + 2.6)
        ax.set_ylim(c[1] - 2.6, c[1] + 2.6)
        ax.set_xlabel("N₁ [ciklus]" if oznake else "z₁")
        ax.set_ylabel("N₂ [ciklus]" if oznake else "z₂")
    spremi(fig, "11-lambda")
    return dict(Q=[[round(x, 4) for x in r] for r in Q.tolist()], rho=rho, a=a.tolist(), okr=okr.tolist(),
                ils=[int(x) for x in ils], d_ils=round(float(norme[0]), 2), d_drugi=round(float(norme[1]), 2),
                omjer=round(float(norme[1] / norme[0]), 2), d_okr=round(d_okr, 2), p_boot=round(float(p_boot), 3),
                mu=int(mu), Qz=[[round(x, 4) for x in r] for r in Qz.tolist()],
                rho_z=round(float(Qz[0, 1] / np.sqrt(Qz[0, 0] * Qz[1, 1])), 3))


def main():
    koordinate()
    trokut()
    dvostruke()
    b = {"lambda": lambda_2d()}
    with open(os.path.join(UDZBENIK, "skripte", "brojke_skice.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
