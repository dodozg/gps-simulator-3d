// REST klijent prema backendu. Isti origin u produkciji; u dev-u Vite proxira.
import type { ConstellationMeta, SandboxExample, SandboxJob, SandboxSize } from "./types";

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

export interface OrbitsStatus { origin: string; fetched_utc?: string; counts: Record<string, number>; cache_age_h: number | null; }
// POST koji ne baca na 4xx: sandbox vraća poruke validacije/ograničenja u tijelu.
async function postRaw<T>(path: string, body: unknown): Promise<{ ok: boolean; status: number; body: T }> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data: unknown = null;
  try { data = await r.json(); } catch { data = null; }
  return { ok: r.ok, status: r.status, body: data as T };
}

export const api = {
  constellation: () => get<ConstellationMeta>("/constellation"),
  orbitsStatus: () => get<OrbitsStatus>("/orbits/status"),
  orbitsRefresh: () => post<OrbitsStatus>("/orbits/refresh", {}),
  glossary: (lang: string) => get<Record<string, GlossaryTerm>>(`/glossary?lang=${lang}`),
  lessons: (lang: string) => get<{ lessons: Lesson[] }>(`/lessons?lang=${lang}`),
  guide: (lang: string) => get<{ md: string; lang: string }>(`/guide?lang=${lang}`),
  rtk: (body: unknown) => post<Record<string, unknown>>("/rtk", body),
  spoofing: (body: unknown) => post<Record<string, unknown>>("/spoofing", body),
  multignss: (body: unknown) => post<Record<string, unknown>>("/multignss", body),
  iono: (body: unknown) => post<Record<string, unknown>>("/iono", body),
  realdata: (body: unknown) => post<Record<string, unknown>>("/realdata", body),
  scenarioList: () => get<{ scenarios: ScenarioMeta[] }>("/scenario/list"),
  scenarioRun: (body: unknown) => post<Record<string, unknown>>("/scenario/run", body),
  scenarioCompare: (body: unknown) => post<Record<string, unknown>>("/scenario/compare", body),
  // istraživački sandbox (pozadinski jobovi)
  sandboxExamples: () => get<{ examples: SandboxExample[]; limits: { max_runs: number; max_epochs: number; max_workers: number } }>("/sandbox/examples"),
  sandboxValidate: (spec: unknown) => post<{ ok: boolean; errors: string[]; size: SandboxSize | null }>("/sandbox/validate", { spec }),
  sandboxRun: (spec: unknown) => postRaw<{ job_id?: string; size?: SandboxSize; detail?: unknown }>("/sandbox/run", { spec }),
  sandboxJob: (id: string) => get<SandboxJob>(`/sandbox/jobs/${id}`),
  sandboxCancel: (id: string) => post<{ ok: boolean }>(`/sandbox/jobs/${id}/cancel`, {}),
  sandboxCsvUrl: (id: string, kind: "aggregate" | "runs" = "aggregate") => `/api/sandbox/jobs/${id}/csv?kind=${kind}`,
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
