// REST klijent prema backendu. Isti origin u produkciji; u dev-u Vite proxira.
import type { ConstellationMeta } from "./types";

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const api = {
  constellation: () => get<ConstellationMeta>("/constellation"),
  glossary: (lang: string) => get<Record<string, GlossaryTerm>>(`/glossary?lang=${lang}`),
  lessons: (lang: string) => get<{ lessons: Lesson[] }>(`/lessons?lang=${lang}`),
  guide: (lang: string) => get<{ md: string; lang: string }>(`/guide?lang=${lang}`),
  rtk: (body: unknown) => post<Record<string, unknown>>("/rtk", body),
  spoofing: (body: unknown) => post<Record<string, unknown>>("/spoofing", body),
  multignss: (body: unknown) => post<Record<string, unknown>>("/multignss", body),
  iono: (body: unknown) => post<Record<string, unknown>>("/iono", body),
  scenarioList: () => get<{ scenarios: ScenarioMeta[] }>("/scenario/list"),
  scenarioRun: (body: unknown) => post<Record<string, unknown>>("/scenario/run", body),
  scenarioCompare: (body: unknown) => post<Record<string, unknown>>("/scenario/compare", body),
};

export interface GlossaryTerm {
  term: string;
  short: string;
  long: string;
  related?: string[];
}
export interface ScenarioMeta {
  file: string;
  name: string;
  description: string;
  lat: number;
  lon: number;
  seconds: number;
  attack: string | null;
}

// Vođena lekcija: koraci koji objašnjavaju i pogone kontrolni panel.
export interface LessonAction {
  do: "place" | "attack" | "time_of_day" | "raim" | "kinematic" | "speed"
    | "play" | "pause" | "reset" | "experiment";
  lat?: number; lon?: number; value?: string | number; hour?: number;
  on?: boolean; tab?: string;
}
export interface LessonStep { text: string; action?: LessonAction; highlight?: string; }
export interface Lesson { id: string; title: string; summary: string; steps: LessonStep[]; }
