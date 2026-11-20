#import "../predlozak.typ": *

#if s-rjesenjima [
#nadnaslov[Prilog A]
#heading(numbering: none)[Rješenja vježbi]

Rješenja vođenih vježbi opisuju što bi se trebalo vidjeti. Točni brojevi ovise o trenutku i mjestu, a trendovi ne. Brojke u rješenjima računskih i istraživačkih vježbi dobivene su skriptama iz #kod("docs/udzbenik/skripte/").

#block[
  #set text(size: 9.5pt)
  #sva-rjesenja()
]
]

#nadnaslov[Prilog #if s-rjesenjima [B] else [A]]
#heading(numbering: none)[Pojmovnik]

Pojmovnik je isti kao u aplikaciji (klik na plavi pojam u telemetriji), preuzet iz #kod("web/content/glossary.hr.json").

#let pojmovi = json("/web/content/glossary.hr.json")
#block[
  #set text(size: 9.5pt)
  #set par(justify: true)
  #for (kljuc, p) in pojmovi.pairs().sorted(key: x => lower(x.at(1).term)) [
    #block(breakable: false, below: 0.7em)[
      #text(font: f-naslov, stretch: 75%, size: 11pt, weight: "semibold", fill: petrol, p.term) \
      #p.short #p.long
    ]
  ]
]

#nadnaslov[Prilog #if s-rjesenjima [C] else [B]]
#heading(numbering: none)[Konstante i parametri simulatora]

Stanje u trenutku izrade knjige. Stupac desno navodi gdje se vrijednost nalazi u kodu.

#block[
  #set text(size: 9pt)
  #show raw: set text(size: 7.5pt)
  #table(
    columns: (1.25fr, 1.35fr, 1fr),
    align: (left, left, left),
    [Veličina], [Vrijednost], [Gdje u kodu],
    table.cell(colspan: 3, fill: luma(240))[_fizikalne konstante_],
    [brzina svjetlosti $c$], [299 792 458 m/s], [#kod("physics_engine.C")],
    [kutna brzina Zemlje $omega_E$], [$7","292 space 115 space 9 dot 10^(-5)$ rad/s], [Sagnac, rotacija ECEF],
    [gravitacijski parametar $mu$], [$3","986 space 004 space 418 dot 10^14$ m³/s²], [#kod("physics_engine.MU")],
    [$J_2$], [$1","082 space 626 space 68 dot 10^(-3)$], [#kod("physics_engine.J2")],
    [WGS-84: $a$, $1\/f$], [6 378 137 m, 298,257 223 563], [#kod("utils.WGS84_A"), #kod("WGS84_F")],
    [polumjer sfere za orbite], [6 371 000 m], [#kod("physics_engine.R_EARTH")],
    [L1, L2], [1575,42 MHz, 1227,60 MHz], [#kod("satellite.py")],
    [čip C/A koda], [1,023 Mčip/s, 1023 čipa, ≈ 293,1 m], [#kod("signal_processing.py")],
    table.cell(colspan: 3, fill: luma(240))[_signal i mjerenje_],
    [primljena snaga (0 dBic, 20 200 km)], [L1 −155,5 dBW, L2 −158,5 dBW], [#kod("signal_model.P_REF_DBW")],
    [šumni pod $N_0$], [≈ −203,8 dBW/Hz], [#kod("signal_model.N0_DBW_HZ")],
    [koherentna integracija, DLL $B_L$, $d$], [20 ms, 2 Hz, 0,5 čipa], [#kod("signal_model.py")],
    [prag zabrave], [28 dB-Hz], [#kod("TRACK_THRESHOLD_DBHZ")],
    [rezidual mjerenja u zenitu], [0,8 m], [#kod("receiver.SIGMA_RES_ZENITH")],
    [elevacijska maska], [5°], [#kod("measurement.py")],
    [najviše satelita u rješenju], [10], [#kod("measurement.MAX_SATS")],
    [pogreška efemerida (OU)], [σ = 1,5 m po osi, τ = 1800 s], [#kod("EPHEMERIS_SIGMA, _TAU")],
    [troposfera u zenitu], [2,4 m], [#kod("physics_engine.py")],
    table.cell(colspan: 3, fill: luma(240))[_navigacija i integritet_],
    [procesni šum EKF-a], [položaj 0,5 m²/s, brzina 1 (m/s)²/s, sat 5 m²/s, drift 1 (m/s)²/s, ISB 0,01 m²/s], [#kod("receiver.Q_*")],
    [$P_"FA"$, $P_"MD"$], [$10^(-5)$, $10^(-3)$], [#kod("raim.RAIM_PFA"), #kod("RAIM_PMD")],
    [HAL], [556 m (RNP 0.3)], [#kod("raim.RAIM_HAL")],
    [grubi RAIM filtar], [6 robusnih σ i 600 m], [#kod("receiver.RAIM_K"), #kod("RAIM_MIN_ABS")],
    [ISB (istina): GAL, GLO, BDS], [+12,5 m, −8 m, +20 m], [#kod("satellite.GNSS_SYSTEMS")],
    table.cell(colspan: 3, fill: luma(240))[_RTK_],
    [šum faze, šum glađenog koda], [2 mm, 0,3 m (zenit)], [#kod("rtk.PHASE_SIGMA_M"), #kod("LIVE_CODE_SIGMA_M")],
    [ostatak atmosfere], [1 ppm duljine baze], [#kod("rtk.ATMO_PPM")],
    [ratio test, $P_"boot"$, maska], [3; 0,999; 10°], [#kod("rtk.RATIO_MIN"), #kod("P_BOOT_MIN"), #kod("LIVE_MASK_DEG")],
  )
]

#nadnaslov[Prilog #if s-rjesenjima [D] else [C]]
#heading(numbering: none)[Literatura]

#set par(hanging-indent: 1.5em, justify: false)
#set text(size: 9.5pt)

Kaplan, E. D., Hegarty, C. J. (ur.): _Understanding GPS/GNSS: Principles and Applications_, 3. izd. Artech House, 2017.

Misra, P., Enge, P.: _Global Positioning System: Signals, Measurements, and Performance_, 2. izd. Ganga-Jamuna Press, 2006.

Teunissen, P. J. G., Montenbruck, O. (ur.): _Springer Handbook of Global Navigation Satellite Systems_. Springer, 2017.

Groves, P. D.: _Principles of GNSS, Inertial, and Multisensor Integrated Navigation Systems_, 2. izd. Artech House, 2013.

IS-GPS-200: _Navstar GPS Space Segment / Navigation User Interfaces_ (sučelje GPS signala i navigacijske poruke).

Betz, J. W., Kolodziejski, K. R.: „Generalized Theory of Code Tracking with an Early-Late Discriminator”, _IEEE Transactions on Aerospace and Electronic Systems_, 45(4), 2009.

Teunissen, P. J. G.: „The least-squares ambiguity decorrelation adjustment: a method for fast GPS integer ambiguity estimation”, _Journal of Geodesy_, 70, 1995.

Brown, R. G.: „A Baseline GPS RAIM Scheme and a Note on the Equivalence of Three RAIM Methods”, _Navigation_, 39(3), 1992.

Klobuchar, J. A.: „Ionospheric Time-Delay Algorithm for Single-Frequency GPS Users”, _IEEE Transactions on Aerospace and Electronic Systems_, AES-23(3), 1987.

Takasu, T.: _RTKLIB: An Open Source Program Package for GNSS Positioning_ (izvor testnih RINEX podataka uz simulator).

GPS Simulator 3D: izvorni kod, dokumentacija (#kod("GPS_Simulator_Documentation.md")) i testovi, #link("https://github.com/dodozg/gps-simulator-3d").
