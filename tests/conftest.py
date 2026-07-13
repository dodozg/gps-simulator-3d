import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _deterministic_rng():
    """Sigurnosna mreža: fiksira i globalni np.random prije svakog testa.

    Nakon RNG refactora engine više NE ovisi o globalnom stanju — svi izvori
    šuma (multipath, AWGN, šum sata, efemeridna pogreška, izbor satelita) primaju
    eksplicitni np.random.Generator koji test/benchmark sjemenjuju
    (`np.random.default_rng(seed)`) i dijele konstelacija i prijemnik.

    Ovo globalno sjeme ostaje samo za slučaj da neki test posredno pozove
    `np.random.*` (npr. u pomoćnom kodu), da rezultat bude reproducibilan.
    """
    np.random.seed(1234)
    yield
