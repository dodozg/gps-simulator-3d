#import "predlozak.typ": *

#show: knjiga.with(
  naslov: [Satelitska\ navigacija\ u simulatoru],
  podnaslov: [GPS i GNSS od signala do integriteta: orbite, pseudoudaljenosti, Kalmanov filtar, RAIM i RTK, uz 67 vježbi u GPS Simulatoru 3D],
  autor: [Domagoj Zoričić i Claude (Anthropic)],
  izdanje: [Izdanje 2026.11. Sve brojke i grafovi izračunati su simulatorom (stanje koda: studeni 2026.).],
)

#sadrzaj()

#include "poglavlja/00-uvod.typ"

#dio("I", [Nebo i vrijeme], [Što je GNSS, u kojim se koordinatama i vremenskim skalama računa i kako se gibaju sateliti.],
  poglavlja: ((1, [Uvod u satelitsku navigaciju]), (2, [Koordinatni sustavi i vrijeme]), (3, [Orbite i konstelacije])))
#include "poglavlja/01-gnss.typ"
#include "poglavlja/02-koordinate-vrijeme.typ"
#include "poglavlja/03-orbite.typ"

#dio("II", [Od signala do mjerenja], [Kako prijemnik iz signala slabijeg od šuma dobiva pseudoudaljenost i što se sve u nju uvuče.],
  poglavlja: ((4, [Signal: kod, korelacija i C/N0]), (5, [Pseudoudaljenost i izvori pogrešaka])))
#include "poglavlja/04-signal.typ"
#include "poglavlja/05-pogreske.typ"

#dio("III", [Od mjerenja do položaja], [Najmanji kvadrati, geometrija i Kalmanov filtar te što donosi više satelitskih sustava.],
  poglavlja: ((6, [Određivanje položaja metodom najmanjih kvadrata]), (7, [Geometrija i DOP]), (8, [Kalmanov filtar]), (9, [Više sustava: multi-GNSS])))
#include "poglavlja/06-najmanji-kvadrati.typ"
#include "poglavlja/07-dop.typ"
#include "poglavlja/08-kalman.typ"
#include "poglavlja/09-multignss.typ"

#dio("IV", [Povjerenje i preciznost], [Kada se položaju smije vjerovati, kako do centimetra i kako se prijemnik napada.],
  poglavlja: ((10, [Integritet: RAIM i zaštitne granice]), (11, [Fazna mjerenja i RTK]), (12, [Ometanje i lažiranje])))
#include "poglavlja/10-raim.typ"
#include "poglavlja/11-rtk.typ"
#include "poglavlja/12-napadi.typ"

#dio("V", [Izvan simulatora], [Isti algoritmi na pravim podacima i vlastita istraživanja u sandboxu.],
  poglavlja: ((13, [Pravi podaci: RINEX i efemeride]), (14, [Istraživački projekti u sandboxu])))
#include "poglavlja/13-pravi-podaci.typ"
#include "poglavlja/14-projekti.typ"

#include "poglavlja/90-dodaci.typ"
