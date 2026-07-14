// Desni panel: live telemetrija + tablica satelita. Pojmovi su klikabilni (učilište).
import { h, clear, term } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import { getMode, onModeChange } from "../lib/prefs";
import type { StateFrame, SatFrame } from "../lib/types";

export function mountTelemetry(container: HTMLElement) {
  let last: StateFrame | null = null;

  function field(labelNode: HTMLElement | string, value: string, cls = ""): HTMLElement {
    const r = h("div", "tel-row " + cls);
    const l = h("div", "tel-label");
    if (typeof labelNode === "string") l.textContent = labelNode;
    else l.appendChild(labelNode);
    const v = h("div", "tel-value", value);
    r.append(l, v);
    return r;
  }

  function satTable(sats: SatFrame[]): HTMLElement {
    const wrap = h("div", "sat-table-wrap");
    wrap.appendChild(h("div", "panel-sub", t("satellite_table")));
    const tbl = h("table", "sat-table");
    const head = h("tr");
    [t("col_sat"), t("col_sys"), t("col_el"), t("col_az"), t("col_used"), t("col_resid")]
      .forEach((c) => head.appendChild(h("th", undefined, c)));
    tbl.appendChild(head);
    const shown = sats
      .filter((s) => s.el != null && s.el >= 0)
      .sort((a, b) => (b.el ?? 0) - (a.el ?? 0));
    for (const s of shown) {
      const tr = h("tr", s.rejected ? "rejected" : s.tracked ? "tracked" : "");
      tr.appendChild(h("td", "mono", s.id));
      tr.appendChild(h("td", undefined, s.system));
      tr.appendChild(h("td", "mono", s.el != null ? s.el.toFixed(0) + "°" : "—"));
      tr.appendChild(h("td", "mono", s.az != null ? s.az.toFixed(0) + "°" : "—"));
      const status = s.rejected ? t("used_rejected") : s.tracked ? t("used_yes") : t("used_visible");
      tr.appendChild(h("td", undefined, status));
      tr.appendChild(h("td", "mono", s.residual_m != null ? s.residual_m.toFixed(0) + " m" : "—"));
      tbl.appendChild(tr);
    }
    wrap.appendChild(tbl);
    return wrap;
  }

  function render(): void {
    clear(container);
    container.appendChild(h("div", "panel-title", t("telemetry")));
    if (!last) { container.appendChild(h("div", "hint", t("no_fix"))); return; }

    const rx = last.receiver;
    const expert = getMode() === "expert";

    if (!rx.placed) {
      container.appendChild(h("div", "hint", t("no_fix")));
      return;
    }

    if (last.attack) {
      const armed = !last.attack_active;
      const b = h("div", "attack-banner" + (armed ? " armed" : ""));
      const name = t("atk_" + last.attack.type);
      b.appendChild(h("span", "attack-dot"));
      b.appendChild(h("span", undefined,
        (last.attack_active ? t("attack_active_banner") : t("attack_armed")) + " — " + name));
      container.appendChild(b);
    }

    if (last.raim_alarm) {
      const banner = h("div", "raim-banner");
      banner.appendChild(term("RAIM", t("raim_alarm")));
      banner.appendChild(h("span", undefined, "  " + last.raim_alarm));
      container.appendChild(banner);
    }

    // koordinate
    if (rx.truth) {
      container.appendChild(field(t(last.kinematic ? "flying" : "truth"),
        `${rx.truth.dms.lat}  ${rx.truth.dms.lon}`));
    }
    if (rx.ekf_initialized && rx.estimate) {
      container.appendChild(field(term("EKF", t("estimate")),
        `${rx.estimate.dms.lat}  ${rx.estimate.dms.lon}`));
      if (rx.error_m != null) {
        container.appendChild(field(t("error"), rx.error_m.toFixed(1) + " m", "accent"));
      }
    } else {
      container.appendChild(h("div", "hint", t("waiting")));
    }

    // integritet i geometrija
    container.appendChild(field(term("GDOP"), rx.gdop != null ? rx.gdop.toFixed(2) : "—"));
    container.appendChild(field(t("sats"),
      `${last.sats_tracked}/${last.sats_total} ${t("tracked")}`));
    if (expert) {
      container.appendChild(field(term("NIS", "NIS/dof"),
        rx.nis_ratio != null ? rx.nis_ratio.toFixed(2) : "—"));
      container.appendChild(field(t("velocity"), (rx.velocity_ms ?? 0).toFixed(1) + " m/s"));
      container.appendChild(field(t("clock"), rx.clock_bias_us.toFixed(1) + " µs"));
    }

    if (expert) container.appendChild(satTable(last.satellites));
  }

  render();
  onLangChange(render);
  onModeChange(render);

  return {
    update(f: StateFrame): void {
      last = f;
      render();
    },
  };
}
