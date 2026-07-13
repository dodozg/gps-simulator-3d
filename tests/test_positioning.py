"""Navigacijski procesor: EKF konvergencija i RAIM izolacija spoofa.

Zamjenjuje ranije ad-hoc skripte test_trilateration.py i test_receiver.py.
"""
import numpy as np

from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef


def _run(gt_lla, seconds, seed=1234):
    """Pokreni kontinuiranu simulaciju.

    Vraća (constellation, greske, alarmi, nis) gdje je `alarmi` popis svih RAIM
    poruka viđenih tijekom cijele simulacije (alarm se resetira svaki epoch).
    Jedan sjemenjeni Generator dijele konstelacija i prijemnik pa je rezultat
    reproducibilan bez oslanjanja na globalno np.random.
    """
    rng = np.random.default_rng(seed)
    constellation = WalkerDeltaConstellation(rng=rng)
    gt = np.array(lla_to_ecef(*gt_lla))
    rx = Receiver(gt, rng=rng)
    errors, alarms, nis = [], [], []
    for t in range(seconds):
        constellation.update_all(float(t))
        rx.receive_signals(constellation, float(t))
        pos, _ = rx.solve_position()
        if pos is not None:
            errors.append(np.linalg.norm(pos - gt))
            if rx.nis_dof:
                nis.append(rx.nis / rx.nis_dof)
        if rx.raim_alarm:
            alarms.append(rx.raim_alarm)
    return constellation, np.array(errors), alarms, np.array(nis)


def test_receiver_sees_satellites():
    rng = np.random.default_rng(1234)
    constellation = WalkerDeltaConstellation(rng=rng)
    gt = np.array(lla_to_ecef(45.815, 15.982, 120.0))  # Zagreb
    rx = Receiver(gt, rng=rng)
    constellation.update_all(0.0)
    signals = rx.receive_signals(constellation, 0.0)
    assert len(signals) >= 4  # dovoljno za rješavanje pozicije
    for sig in signals:
        assert sig["pseudorange"] > 0


def test_ekf_converges():
    _, errors, _, _ = _run((51.5074, -0.1278, 50.0), seconds=120)  # London
    assert len(errors) > 30
    converged = errors[-30:]
    # Pristrani multipath + troposfera daju "pod" reda ~50-60 m; filter mora
    # konvergirati znatno ispod bučnog cold-start rješenja (~200 m).
    assert converged.mean() < 150.0
    assert converged.mean() < errors[0]


def test_filter_is_consistent():
    # NIS/dof mora ostati blizu 1 (filter niti preoptimističan niti prekonzervativan).
    # Štiti podešeni SIGMA_ZENITH od regresije.
    _, _, _, nis = _run((51.5074, -0.1278, 50.0), seconds=120)
    assert len(nis) > 30
    assert 0.5 < nis[-60:].mean() < 2.0


def test_raim_rejects_spoofed_satellite():
    # Spoof na SAT_0_0 se aktivira nakon t=200 s; simuliraj preko toga.
    constellation, errors, alarms, _ = _run((51.5, -0.13, 50.0), seconds=320)
    assert constellation.satellites[0].is_spoofed
    # RAIM je barem jednom izolirao uljeza tijekom spoof prozora.
    assert any("SAT_0_0" in a for a in alarms)
    # Unatoč lažnih 6 km na jednom satelitu, rješenje ostaje upotrebljivo.
    assert errors[-1] < 200.0


def test_raim_screen_handles_clean_and_multiple_outliers():
    rx = Receiver(np.array(lla_to_ecef(45.0, 15.0, 100.0)))
    # Čiste inovacije (normalni multipath, desetci metara) -> nista se ne odbacuje.
    clean = [12.0, -8.0, 25.0, -15.0, 5.0, -20.0, 18.0]
    assert rx._raim_screen(clean) == set()
    # Dva gruba blundera (6 km i 3 km) medju dobrima -> oba se odbacuju (iterativno).
    inn = [10.0, -5.0, 6000.0, 20.0, -12.0, 3000.0, 8.0]
    assert rx._raim_screen(inn) == {2, 5}


def test_selection_is_deterministic_and_no_cheat():
    rng = np.random.default_rng(0)
    constellation = WalkerDeltaConstellation(rng=rng)
    constellation.update_all(0.0)
    gt = np.array(lla_to_ecef(0.0, 0.0, 0.0))
    rx = Receiver(gt, rng=rng)
    pairs = [(s, s.get_signal(0.0)) for s in constellation.satellites]
    # Iz procjene: deterministicki (isti ulaz -> isti izlaz) i tocno max_sats.
    a = rx.select_best_satellites(pairs, max_sats=6, ref_pos=gt)
    b = rx.select_best_satellites(pairs, max_sats=6, ref_pos=gt)
    assert len(a) == 6
    assert [x[0].sat_id for x in a] == [x[0].sat_id for x in b]
    # Hladan start (bez procjene) uzima sve (do granice), ne optimizira geometriju.
    cold = rx.select_best_satellites(pairs, max_sats=6, ref_pos=None)
    assert len(cold) >= 6
