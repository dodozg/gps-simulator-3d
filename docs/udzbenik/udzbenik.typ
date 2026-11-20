#import "predlozak.typ": *

#show: knjiga.with(
  naslov: "Satelitska navigacija u simulatoru",
  podnaslov: [GPS i GNSS od signala do integriteta \ — udžbenik s vježbama u GPS Simulatoru 3D],
  autor: "GPS Simulator 3D",
  datum: "2026.",
)

#include "poglavlja/00-uvod.typ"

#outline(title: "Sadržaj", depth: 2, indent: auto)

#include "poglavlja/01-gnss.typ"
#include "poglavlja/02-koordinate-vrijeme.typ"
#include "poglavlja/03-orbite.typ"
#include "poglavlja/04-signal.typ"
#include "poglavlja/05-pogreske.typ"
#include "poglavlja/06-najmanji-kvadrati.typ"
#include "poglavlja/07-dop.typ"
#include "poglavlja/08-kalman.typ"
#include "poglavlja/09-multignss.typ"
#include "poglavlja/10-raim.typ"
#include "poglavlja/11-rtk.typ"
#include "poglavlja/12-napadi.typ"
#include "poglavlja/13-pravi-podaci.typ"
#include "poglavlja/14-projekti.typ"

#include "poglavlja/90-dodaci.typ"
