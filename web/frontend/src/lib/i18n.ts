// Dvojezično sučelje (HR/EN) s reaktivnim prekidačem jezika.
export type Lang = "hr" | "en";

type Dict = Record<string, string>;

const HR: Dict = {
  app_title: "GPS Simulator 3D",
  app_subtitle: "Kontrolni centar i GPS učilište",
  connecting: "Spajanje…",
  connected: "Povezano",
  disconnected: "Veza prekinuta — ponovno spajanje…",
  // kontrole
  controls: "Kontrole",
  play: "Pokreni",
  pause: "Pauza",
  speed: "Brzina",
  reset: "Poništi",
  place_hint: "Dvoklik na globus postavlja prijemnik",
  kinematic: "Kinematički (let)",
  raim: "RAIM integritet",
  time_of_day: "Doba dana (ionosfera)",
  show_orbits: "Orbite",
  show_rays: "Signalne zrake",
  show_labels: "Oznake satelita",
  systems: "Sustavi",
  mode_beginner: "Početnik",
  mode_expert: "Stručnjak",
  // telemetrija
  telemetry: "Telemetrija",
  no_fix: "NEMA FIXA — klikni na globus",
  waiting: "čekam rješenje…",
  truth: "Istina",
  estimate: "Procjena",
  flying: "Let",
  error: "Greška",
  velocity: "Brzina",
  clock: "Sat prijemnika",
  sats: "Sateliti",
  tracked: "praćeni",
  satellite_table: "Sateliti u vidokrugu",
  col_sat: "Sat",
  col_sys: "Sustav",
  col_el: "Elev",
  col_az: "Azimut",
  col_used: "Status",
  col_resid: "Rezidual",
  used_yes: "koristi se",
  used_rejected: "RAIM odbacio",
  used_visible: "vidljiv",
  raim_alarm: "RAIM ALARM",
  attack: "Napad",
  attack_none: "nema",
  // pojmovnik
  learn_more: "Detaljnije",
  related: "Povezano",
  academy: "Učilište",
};

const EN: Dict = {
  app_title: "GPS Simulator 3D",
  app_subtitle: "Control Center & GPS Academy",
  connecting: "Connecting…",
  connected: "Connected",
  disconnected: "Disconnected — reconnecting…",
  controls: "Controls",
  play: "Play",
  pause: "Pause",
  speed: "Speed",
  reset: "Reset",
  place_hint: "Double-click the globe to place the receiver",
  kinematic: "Kinematic (flight)",
  raim: "RAIM integrity",
  time_of_day: "Time of day (ionosphere)",
  show_orbits: "Orbits",
  show_rays: "Signal rays",
  show_labels: "Satellite labels",
  systems: "Systems",
  mode_beginner: "Beginner",
  mode_expert: "Expert",
  telemetry: "Telemetry",
  no_fix: "NO FIX — click the globe",
  waiting: "waiting for solution…",
  truth: "Truth",
  estimate: "Estimate",
  flying: "Flight",
  error: "Error",
  velocity: "Velocity",
  clock: "Receiver clock",
  sats: "Satellites",
  tracked: "tracked",
  satellite_table: "Satellites in view",
  col_sat: "Sat",
  col_sys: "System",
  col_el: "Elev",
  col_az: "Azimuth",
  col_used: "Status",
  col_resid: "Residual",
  used_yes: "in use",
  used_rejected: "RAIM rejected",
  used_visible: "visible",
  raim_alarm: "RAIM ALARM",
  attack: "Attack",
  attack_none: "none",
  learn_more: "Learn more",
  related: "Related",
  academy: "Academy",
};

const DICTS: Record<Lang, Dict> = { hr: HR, en: EN };

let lang: Lang = ((localStorage.getItem("lang") as Lang) || "hr");
const listeners = new Set<() => void>();

export function t(key: string): string {
  return DICTS[lang][key] ?? DICTS.en[key] ?? key;
}
export function getLang(): Lang {
  return lang;
}
export function setLang(l: Lang): void {
  lang = l;
  localStorage.setItem("lang", l);
  document.documentElement.lang = l;
  listeners.forEach((f) => f());
}
export function onLangChange(f: () => void): () => void {
  listeners.add(f);
  return () => listeners.delete(f);
}
