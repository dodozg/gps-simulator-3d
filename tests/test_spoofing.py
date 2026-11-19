"""Spoofing/jamming lab: svaki napad mora pokazati očekivano ponašanje obrane."""
import numpy as np

from spoofing import (CoordinatedSpoof, NaiveMultiSpoof, Meaconing, Jamming,
                      run_attack)

LAT, LON, ALT = 45.815, 15.982, 120.0
START, END, SECS = 60.0, 210.0, 260


def _alarms_in_window(data):
    s, e = data["window"]
    return [t for (t, _) in data["alarms"] if s <= t <= e]


def _median_err_in_window(data):
    s, e = data["window"]
    vals = [err for (t, err) in data["errors"] if s <= t <= e]
    return float(np.median(vals)) if vals else 0.0


def _final_err(data):
    return data["errors"][-1][1] if data["errors"] else 0.0


def test_coordinated_spoof_evades_raim_and_pulls_position():
    atk = CoordinatedSpoof(offset_e=600.0, start=START, end=END)
    data = run_attack(LAT, LON, ALT, atk, SECS, seed=1234)
    # Reziduali ostaju konzistentni -> RAIM NE alarmira tijekom napada...
    assert len(_alarms_in_window(data)) == 0
    # ...a pozicija tiho odšeta blizu ciljne točke (~600 m od istine).
    assert _final_err(data) > 400.0
    target_err_end = [err for (t, err) in data["target_err"] if t >= END - 1]
    assert np.median(target_err_end) < 150.0


def test_naive_multispoof_is_caught_by_raim():
    atk = NaiveMultiSpoof(n=2, bias_m=5000.0, start=START, end=END)
    data = run_attack(LAT, LON, ALT, atk, SECS, seed=1234)
    # Robusni RAIM (#2) izolira nezavisne outliere...
    assert len(_alarms_in_window(data)) > 40
    # ...pa greška ostaje ograničena unatoč velikim pomacima.
    assert _median_err_in_window(data) < 300.0


def test_meaconing_is_absorbed_by_receiver_clock():
    atk = Meaconing(delay_m=4000.0, start=START, end=END)
    data = run_attack(LAT, LON, ALT, atk, SECS, seed=1234)
    # Uniformni pomak upije se u sat prijemnika -> pozicija se ne miče, RAIM šuti.
    assert len(_alarms_in_window(data)) == 0
    assert _median_err_in_window(data) < 200.0


def test_jamming_denies_service_without_raim():
    atk = Jamming(js_db=40.0, start=START, end=END)
    data = run_attack(LAT, LON, ALT, atk, SECS, seed=1234)
    # Ometanje ruši broj praćenih satelita i gubi fix; RAIM tu ne alarmira
    # (nije riječ o lažnim mjerenjima nego o gubitku signala).
    assert len(data["fix_lost"]) > 0
    assert int(data["tracked"].min()) < 6
    assert len(data["alarms"]) == 0


def test_attack_stop_ends_effect():
    # `stop` gasi napad: nakon njega jamming više ne guši signal. Jamming djeluje
    # kroz signalni model (J/N → C/N0_eff → zabrava), ne mijenja gotova mjerenja.
    from spoofing import Jamming
    atk = Jamming(js_db=60.0, start=10.0, end=20.0, stop=30.0)
    assert not atk.is_active(5.0) and atk.is_active(25.0) and not atk.is_active(31.0)
    assert atk.jammer_jn_db(5.0) == 0.0 and atk.jammer_jn_db(15.0) == 30.0   # rampa
    assert atk.jammer_jn_db(25.0) == 60.0 and atk.jammer_jn_db(31.0) == 0.0  # drži, pa stop
    sats = [("S", np.array([0.0, 0.0, 26_000e3]))]         # satelit u zenitu
    rx = np.array([0.0, 0.0, 6_371e3])
    assert atk.surviving(sats, 25.0, rx) == set()           # aktivan -> zabrava izgubljena
    assert atk.surviving(sats, 31.0, rx) == {"S"}           # nakon stop-a prati se
    # apply() ne dira gotove pseudoudaljenosti (ometač je u signalu, ne post-hoc)
    sigs = [{"sat_pos": sats[0][1], "pseudorange": 2.0e7}]
    atk.apply(sigs, 25.0, rx, np.random.default_rng(0))
    assert len(sigs) == 1 and sigs[0]["pseudorange"] == 2.0e7
