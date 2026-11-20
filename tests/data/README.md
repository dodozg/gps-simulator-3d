# Testni podaci — pravi GNSS (RINEX / SP3)

Sve datoteke potječu iz **RTKLIB** repozitorija (T. Takasu), grana `rtklib_2.4.3`,
direktorij `test/data/` — https://github.com/tomojitakasu/RTKLIB
Licenca: **BSD 2-clause** (Copyright (c) 2007-2020, T. Takasu). Tekst licence:
https://github.com/tomojitakasu/RTKLIB/blob/rtklib_2.4.3/LICENSE.txt
Izvorni podaci: GSI GEONET (Japan) i IGS (broadcast + final orbite).

Datoteke se samo ČITAJU kao tekst (parseri u `rinex.py`); ništa se ne izvršava.

| Datoteka | Izvor (RTKLIB `test/data/…`) | Sadržaj | Obrada |
|---|---|---|---|
| `07590920.05o` | `rinex/07590920.05o` | RINEX 2.10 opažanja, GEONET stanica 0759, Trimble 5700, 2005-04-02 00:00–00:59:30 GPST, 30 s (120 epoha), L1/C1/L2/P2 | bez izmjene (68 KB) |
| `07590920.05n` | `rinex/07590920.05n` | RINEX 2.10 GPS navigacija iste stanice (162 efemeride, Klobuchar α/β u zaglavlju) | bez izmjene (95 KB) |
| `brdc1820_trim.10n` | `rinex/brdc1820.10n` | IGS spojena broadcast navigacija, 2010-07-01 | zadržani samo zapisi s toc 00:00–04:00 |
| `igs15904_trim.sp3` | `sp3/igs15904.sp3` | IGS final precizne orbite + satovi (SP3-c, 15 min), GPS tjedan 1590 dan 4 = 2010-07-01 | zadržane epohe 00:00–03:00 (13) |

Skraćivanje: zaglavlja su zadržana netaknuta, uklonjeni su samo cijeli zapisi
(navigacija: zapisi izvan 00–04 h; SP3: epohe nakon 03:00) i završni razmaci
u skraćenim datotekama. Linije su LF.

Namjena:
* `07590920.05o` + `.05n` — SPP na pravim podacima (`realdata.py`, `/api/realdata`,
  `tests/test_realdata.py`). Referenca: APPROX POSITION XYZ iz zaglavlja.
* `brdc1820_trim.10n` + `igs15904_trim.sp3` — NEOVISNA provjera `ephemeris.py`:
  broadcast orbite moraju se slagati s IGS final orbitama na razini ~1–3 m.
