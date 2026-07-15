// "Fly to" — pretraga grada ili koordinata pa let kamere. Bez vanjskog geokodera
// (CSP blokira mrežu): ugrađena lista gradova + parsiranje koordinata. Opcijski
// odmah postavi prijemnik na odabranu točku.
import { h } from "../lib/dom";
import { t } from "../lib/i18n";
import type { Globe } from "../globe/globe";

interface City { name: string; lat: number; lon: number; }

// Reprezentativan skup: svjetske metropole + hrvatski gradovi. Dovoljno za
// demo/učenje; lako proširivo.
const CITIES: City[] = [
  { name: "Zagreb", lat: 45.815, lon: 15.982 },
  { name: "Split", lat: 43.508, lon: 16.44 },
  { name: "Rijeka", lat: 45.327, lon: 14.442 },
  { name: "Osijek", lat: 45.555, lon: 18.694 },
  { name: "Dubrovnik", lat: 42.641, lon: 18.108 },
  { name: "Ljubljana", lat: 46.056, lon: 14.508 },
  { name: "Beograd", lat: 44.787, lon: 20.449 },
  { name: "Wien", lat: 48.208, lon: 16.373 },
  { name: "Budapest", lat: 47.497, lon: 19.04 },
  { name: "München", lat: 48.135, lon: 11.582 },
  { name: "Berlin", lat: 52.52, lon: 13.405 },
  { name: "Paris", lat: 48.857, lon: 2.352 },
  { name: "London", lat: 51.507, lon: -0.128 },
  { name: "Madrid", lat: 40.417, lon: -3.703 },
  { name: "Roma", lat: 41.903, lon: 12.496 },
  { name: "Amsterdam", lat: 52.37, lon: 4.895 },
  { name: "Zürich", lat: 47.377, lon: 8.542 },
  { name: "Stockholm", lat: 59.329, lon: 18.069 },
  { name: "Oslo", lat: 59.914, lon: 10.752 },
  { name: "Helsinki", lat: 60.169, lon: 24.938 },
  { name: "Athina", lat: 37.984, lon: 23.728 },
  { name: "Istanbul", lat: 41.008, lon: 28.978 },
  { name: "Moskva", lat: 55.756, lon: 37.617 },
  { name: "Dubai", lat: 25.205, lon: 55.271 },
  { name: "New York", lat: 40.713, lon: -74.006 },
  { name: "Washington", lat: 38.895, lon: -77.037 },
  { name: "San Francisco", lat: 37.775, lon: -122.419 },
  { name: "Los Angeles", lat: 34.052, lon: -118.244 },
  { name: "Chicago", lat: 41.878, lon: -87.63 },
  { name: "Toronto", lat: 43.653, lon: -79.383 },
  { name: "Mexico City", lat: 19.433, lon: -99.133 },
  { name: "Bogotá", lat: 4.711, lon: -74.072 },
  { name: "Lima", lat: -12.046, lon: -77.043 },
  { name: "São Paulo", lat: -23.551, lon: -46.633 },
  { name: "Buenos Aires", lat: -34.604, lon: -58.382 },
  { name: "Kapstadt", lat: -33.925, lon: 18.424 },
  { name: "Nairobi", lat: -1.286, lon: 36.817 },
  { name: "Cairo", lat: 30.044, lon: 31.236 },
  { name: "Lagos", lat: 6.524, lon: 3.379 },
  { name: "Delhi", lat: 28.614, lon: 77.209 },
  { name: "Mumbai", lat: 19.076, lon: 72.878 },
  { name: "Singapore", lat: 1.352, lon: 103.82 },
  { name: "Bangkok", lat: 13.756, lon: 100.502 },
  { name: "Hong Kong", lat: 22.319, lon: 114.17 },
  { name: "Beijing", lat: 39.904, lon: 116.407 },
  { name: "Shanghai", lat: 31.23, lon: 121.474 },
  { name: "Tokyo", lat: 35.68, lon: 139.69 },
  { name: "Seoul", lat: 37.567, lon: 126.978 },
  { name: "Sydney", lat: -33.869, lon: 151.209 },
  { name: "Auckland", lat: -36.848, lon: 174.763 },
];

const norm = (s: string) =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();

// "45.815, 15.982" ili "45.815 15.982" -> [lat, lon] ako su u valjanom rasponu.
function parseCoords(q: string): [number, number] | null {
  const m = q.match(/(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)/);
  if (!m) return null;
  const lat = Number(m[1]), lon = Number(m[2]);
  if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) return [lat, lon];
  return null;
}

function matchCity(q: string): City | null {
  const n = norm(q);
  if (!n) return null;
  return CITIES.find((c) => norm(c.name) === n)
    ?? CITIES.find((c) => norm(c.name).startsWith(n))
    ?? CITIES.find((c) => norm(c.name).includes(n))
    ?? null;
}

export function mountFlyTo(parent: HTMLElement, globe: Globe,
                           onPlace: (lat: number, lon: number) => void): void {
  const box = h("div", "flyto");
  const input = h("input", "flyto-input") as HTMLInputElement;
  input.type = "search";
  input.placeholder = t("flyto_ph");
  input.setAttribute("list", "flyto-cities");
  input.setAttribute("autocomplete", "off");
  const list = h("datalist") as HTMLDataListElement;
  list.id = "flyto-cities";
  for (const c of CITIES) {
    const o = h("option") as HTMLOptionElement;
    o.value = c.name; list.appendChild(o);
  }
  const placeBtn = h("button", "flyto-place", "📍") as HTMLButtonElement;
  placeBtn.title = t("flyto_place");
  box.append(input, placeBtn, list);
  parent.appendChild(box);

  function resolve(): [number, number] | null {
    const q = input.value;
    return parseCoords(q) ?? (matchCity(q) ? [matchCity(q)!.lat, matchCity(q)!.lon] : null);
  }
  function fly(place: boolean): void {
    const p = resolve();
    if (!p) { box.classList.add("flyto-miss"); setTimeout(() => box.classList.remove("flyto-miss"), 600); return; }
    const [lat, lon] = p;
    globe.flyTo(lat, lon, place ? 900_000 : 500_000);
    if (place) onPlace(lat, lon);
  }

  input.addEventListener("keydown", (e) => { if (e.key === "Enter") fly(false); });
  placeBtn.addEventListener("click", () => fly(true));
}
