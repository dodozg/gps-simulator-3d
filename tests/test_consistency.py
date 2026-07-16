"""Zero-noise konzistencijski test — štiti od klase "istina curi u prijemnik" bugova.

U ideal modu (Receiver(..., ideal=True) + constellation.update_all(t, ideal=True))
UGASE se SVI stohastički i kvantizacijski izvori pogreške:
  - multipath i AWGN u RF kanalu,
  - korelatorska kvantizacija (savršeno mjerenje dometa umjesto FFT korelacije),
  - pogreška efemerida (broadcast_pos == prava pozicija),
  - Allanov šum satova (ostaje samo deterministički drift/relativnost, koji se
    ionako egzaktno poništava broadcast korekcijom).

Preostaju SAMO deterministički modeli koje prijemnik i sam korigira: geometrija,
troposfera (Hopfield), Sagnac, ionosfera (iono-free), inter-system bias, relativnost.

TVRDNJA: ako svaki član koji se KORIGIRA ima egzaktno odgovarajući član UBRIZGAN u
mjerenje, rezidual pozicije mora pasti na ~strojnu preciznost (~10 µm). Bilo koja
veća, sustavna vrijednost odaje nekonzistentnost injekcije↔korekcije.

To je točno klasa buga kao nekadašnji Sagnac: prijemnik je korigirao efekt (h_x +=
sagnac) kojeg mjerenje nije sadržavalo -> ~25 m pristranost prema istoku, skrivena u
multipath šumu i "objašnjena" napuhanim SIGMA_ZENITH-om. Šum takve bugove maskira;
ovaj ih test čini glasnima jer u ideal modu nema šuma iza kojeg bi se sakrili
(rezidual skoči s ~10 µm na metre/desetke metara — svaki nedostajući/suvišni član je
≥ decimetre: Sagnac ~25 m, ISB 8–20 m, ionosfera i tropo metri).
"""
import numpy as np

from satellite import MultiGNSSConstellation
from receiver import Receiver
from utils import lla_to_ecef


def _run_ideal(lla, seconds, seed=1234):
    """Vozi konstelaciju i prijemnik u ideal modu; vrati niz pogrešaka pozicije [m]."""
    rng = np.random.default_rng(seed)
    con = MultiGNSSConstellation(rng=rng)
    gt = np.array(lla_to_ecef(*lla))
    rx = Receiver(gt, rng=rng, ideal=True)
    errs = []
    for t in range(seconds):
        con.update_all(float(t), ideal=True)
        rx.receive_signals(con, float(t))
        pos, _ = rx.solve_position()
        if pos is not None:
            errs.append(np.linalg.norm(pos - gt))
    return np.array(errs)


# Lokacije koje brzo konvergiraju (niska/umjerena nadmorska visina, razne širine).
# Sve postignu ~10 µm; prag 1 cm je ~1000× iznad tog poda i ~500× ispod noisy
# točnosti (~5 m), pa robusno prolazi, a svaka model-nekonzistentnost ga probije.
_EXACT_LOCATIONS = [
    (45.815, 15.982, 120.0),    # Zagreb
    (51.5074, -0.1278, 50.0),   # London
    (0.0, 0.0, 0.0),            # Greenwich/ekvator
    (35.68, 139.77, 40.0),      # Tokio
    (61.22, -149.9, 30.0),      # Anchorage (visoka širina)
]


def test_zero_noise_solution_is_exact():
    """Bez ijednog izvora šuma rješenje mora biti na ~mm (tipično ~10 µm).

    Dokaz da je svaki ubrizgani član egzaktno poništen odgovarajućom korekcijom —
    nema "curenja istine". Regresijski čuvar: reintrodukcija Sagnac-tipa buga
    (korekcija bez injekcije ili obrnuto) diže rezidual s µm na metre.
    """
    for lla in _EXACT_LOCATIONS:
        errs = _run_ideal(lla, seconds=120)
        assert len(errs) > 60
        final = errs[-1]
        assert final < 0.01, (
            f"{lla}: zero-noise rezidual {final * 100:.4f} cm > 1 cm — "
            "moguća injekcija↔korekcija nekonzistentnost (curenje istine u prijemnik)"
        )


def test_zero_noise_converges_not_floored():
    """Rezidual se mora asimptotski smanjivati prema nuli, a ne zaustaviti na 'podu'.

    Pod (konstantan zaostatak) značio bi zaostalu SUSTAVNU pogrešku — model koji ne
    konvergira na istinu. Quito (2850 m, ekvatorijalna geometrija) konvergira sporo
    zbog velike rampe sata prijemnika (~300 m/s) pa je idealan za ovu provjeru:
    kasni prozor mora biti bitno bolji od ranog i dobrano ispod centimetra.
    """
    errs = _run_ideal((-0.18, -78.47, 2850.0), seconds=200)   # Quito
    assert len(errs) > 100
    early = errs[20:50].mean()
    late = errs[-30:].mean()
    assert late < early, f"ne konvergira: rani {early*100:.3f} cm, kasni {late*100:.3f} cm"
    assert late < 0.02, f"kasni rezidual {late*100:.3f} cm > 2 cm (zaostala sustavna pogreška?)"
