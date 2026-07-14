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
  el?: number;
  az?: number;
  rejected?: boolean;
  residual_m?: number;
}

export interface ReceiverFrame {
  placed: boolean;
  ekf_initialized: boolean;
  truth?: PosBlock;
  estimate?: PosBlock;
  error_m?: number | null;
  velocity_ms?: number;
  gdop: number | null;
  nis: number | null;
  nis_dof: number;
  nis_ratio: number | null;
  clock_bias_us: number;
}

export interface StateFrame {
  sim_time: number;
  playing: boolean;
  time_scale: number;
  kinematic: boolean;
  raim_enabled: boolean;
  iono_tow0: number;
  attack: Record<string, unknown> | null;
  raim_alarm: string | null;
  sats_total: number;
  sats_tracked: number;
  receiver: ReceiverFrame;
  satellites: SatFrame[];
}

export interface ConstellationMeta {
  omega_e: number;
  r_earth: number;
  gps: { a: number; e: number; i: number; w: number; planes: number[]; n_sats: number };
  systems: Record<string, { alt: number; inc: number; isb_m: number; planes: number; sats: number }>;
}
