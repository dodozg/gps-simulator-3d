# Primjeri istraživačkog sandboxa / Research sandbox examples

Pokretanje / run: `python sandbox.py run sandbox/examples/<spec>.json --workers 4 --plot`
(rezultati u `results/<ime>/`: `results.json`, `results.csv`, `runs.csv`, `plot_*.png`).
Svi primjeri koriste `t0_random_s` — svako sjeme dobije drugu geometriju
konstelacije (Monte Carlo i šuma i geometrije) / every seed also samples a different
constellation geometry.

| Spec | Istraživačko pitanje / research question |
|------|-------------------------------------------|
| `raim_roc.json` | Kolika je vjerojatnost detekcije RAIM-a u ovisnosti o veličini kvara sata jednog satelita, za P_FA = 1e-2 … 1e-7? (ROC-olika studija; napad `sat_fault`) / RAIM detection probability vs single-satellite clock-fault size for several P_FA values. |
| `spoof_offset.json` | Koliko daleko koordinirani spoof odvuče rješenje i koliko često je greška veća od HPL-a bez alarma (misleading information)? / Coordinated spoof offset vs final error and misleading-information rate. |
| `jamming_jn.json` | Pri kojem J/N se gubi fix i integritet — GPS sam vs četiri sustava? / Jamming J/N vs availability, GPS-only vs four constellations. |
| `multignss_mask.json` | Koliko multi-GNSS pomaže u urbanom kanjonu (visoka elevacijska maska): dostupnost, HPL, dostupnost integriteta uz HAL = 100 m? / Multi-GNSS vs elevation mask (availability, HPL). |
| `ekf_vs_wls.json` | Koliko EKF dobiva nad snapshot WLS-om na istim mjerenjima, na pet lokacija? / EKF vs snapshot WLS accuracy across seeds and locations (paired). |
