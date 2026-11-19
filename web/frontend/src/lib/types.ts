// Oblik podataka koje backend šalje (vidi web/backend/serialize.py).
export interface LLA { lat: number; lon: number; alt: number; }
export interface DMS { lat: string; lon: string; }
export interface PosBlock { lla: LLA; dms: DMS; ecef: [number, number, number]; }

export interface SatFrame {
  id: string;
  system: string;
  ecef: [number, number, number];
  lla: LLA;
  tracked: boolean;
  enabled?: boolean;
  el?: number;
  az?: number;
  rejected?: boolean;
  residual_m?: number;
  params?: { clock_offset_m: number; alt_km: number; inc_deg: number; lan_deg: number; ecc: number; pos_offset_m: number };
}

export interface SystemInfo {
  on: boolean;
  total: number;
  enabled: number;
  tracked: number;
}

export interface ReceiverFrame {
  placed: boolean;
  ekf_initialized: boolean;
  truth?: PosBlock;
  estimate?: PosBlock;
  error_m?: number | null;
  velocity_ms?: number;
  velocity_true_ms?: number;
  gdop: number | null;
  nis: number | null;
  nis_dof: number;
  nis_ratio: number | null;
  clock_bias_us: number;
  // Epoha bez dovoljno neovisnih mjerenja za sve nepoznanice (položaj+sat+ISB):
  // rješenje se drži na apriornoj kovarijanci, DOP-a nema.
  underdetermined?: boolean;
  // Integritet (statistički RAIM): test reziduala, isključeni sateliti, zaštitne granice.
  integrity?: IntegrityFrame;
  isb?: Array<{ system: string; est: number | null; true: number }>;
}

export interface IntegrityFrame {
  status: "ok" | "excluded" | "alarm" | "unavailable" | "disabled";
  test?: number | null;        // chi-kvadrat statistika reziduala
  threshold?: number | null;   // prag za zadani P_FA
  dof?: number;                // stupnjevi slobode (redundancija)
  hpl?: number | null;         // horizontalna zaštitna granica [m]
  vpl?: number | null;         // vertikalna zaštitna granica [m]
  hal?: number | null;         // horizontalna granica uzbune [m]
  val?: number | null;         // vertikalna granica uzbune [m] (null = nema)
  available?: boolean;         // HPL ≤ HAL (i VPL ≤ VAL)
  excluded?: string[];         // isključeni sateliti
  pfa?: number;
  pmd?: number;
}

export interface AttackSpec {
  type: "coordinated" | "naive" | "meaconing" | "jamming";
  start: number;
  end: number;
  offset_e?: number;
  offset_n?: number;
  offset_u?: number;
  [k: string]: unknown;
}

export interface AttackOverlay {
  type: string;
  active: boolean;
  target_ecef?: [number, number, number];
  radius_m?: number;
}

export interface StateFrame {
  sim_time: number;
  playing: boolean;
  time_scale: number;
  time_scale_actual?: number;   // ostvareno ubrzanje (0 = pauza/nepoznato)
  kinematic: boolean;
  raim_enabled: boolean;
  iono_tow0: number;
  tow_now?: number;             // doba dana koje model UPRAVO koristi (tow0 + sim_time)
  attack: AttackSpec | null;
  attack_active: boolean;
  attack_overlay: AttackOverlay | null;
  raim_alarm: string | null;
  sats_total: number;
  sats_tracked: number;
  receiver: ReceiverFrame;
  satellites: SatFrame[];
  systems?: Record<string, SystemInfo>;
}

export interface ConstellationMeta {
  omega_e: number;
  r_earth: number;
  gps: { a: number; e: number; i: number; w: number; planes: number[]; n_sats: number };
  systems: Record<string, { alt: number; inc: number; isb_m: number; planes: number; sats: number }>;
}
