// Razina prikaza: Početnik (manje žargona) / Stručnjak (puni detalj).
export type Mode = "beginner" | "expert";

let mode: Mode = ((localStorage.getItem("mode") as Mode) || "beginner");
const listeners = new Set<() => void>();

export const getMode = (): Mode => mode;
export const setMode = (m: Mode): void => {
  mode = m;
  localStorage.setItem("mode", m);
  listeners.forEach((f) => f());
};
export const onModeChange = (f: () => void): (() => void) => {
  listeners.add(f);
  return () => listeners.delete(f);
};
