import os
import pyvista as pv
import numpy as np
import time
from satellite import WalkerDeltaConstellation
from receiver import Receiver
from physics_engine import R_EARTH, calculate_terrain_elevation
from utils import ecef_to_lla, lla_to_ecef, format_dms

# --- Paleta sučelja (0..1 RGB) ------------------------------------------------
C_CYAN  = (0.14, 0.83, 0.93)   # akcent / naslov
C_GREEN = (0.24, 0.85, 0.60)   # lock / dobro
C_AMBER = (0.98, 0.75, 0.16)   # istina / upozorenje-blago
C_RED   = (0.97, 0.42, 0.42)   # alarm / spoof
C_TEXT  = (0.90, 0.93, 0.97)   # osnovni tekst
C_DIM   = (0.56, 0.63, 0.74)   # sekundarni tekst
C_PANEL = (0.05, 0.07, 0.11)   # pozadina panela

WIN_W, WIN_H = 1280, 800
OMEGA_E = 7.2921159e-5         # rad/s — Zemljina rotacija (kao u physics_engine)


def terrain_colors(elevations):
    """Hipsometrijsko bojanje terena po visini -> (N,3) uint8 RGB.

    Boje se normaliziraju na STVARNI raspon podataka odvojeno za more i kopno
    (granica je razina mora, 0 m): more se rasteže od obale do najdublje točke,
    a kopno od obale do najvišeg vrha. Time snijeg (bijelo) pada samo na prave
    vrhove, umjesto da se pola globusa zabijeli kad teren ima velike amplitude.
    Koristi se kao per-vertex RGB (rgb=True) -> izbjegava scalars+cmap shader bug.
    """
    e = np.asarray(elevations, dtype=float)
    out = np.empty((e.size, 3), dtype=np.uint8)

    sea = e < 0.0
    land = ~sea

    # More: batimetrija (0 uz obalu -> 1 najdublje). Tirkizno plitko -> tamna navy.
    if sea.any():
        e_min = e[sea].min()
        depth = np.clip(e[sea] / e_min, 0.0, 1.0) if e_min < 0 else np.zeros(sea.sum())
        d_stops = [0.0, 0.35, 1.0]
        out[sea, 0] = np.interp(depth, d_stops, [ 34,  22,   7])
        out[sea, 1] = np.interp(depth, d_stops, [126,  84,  22])
        out[sea, 2] = np.interp(depth, d_stops, [158, 168,  66])

    # Kopno: hipsometrija (0 uz obalu -> 1 vrh). Zeleno -> tan -> smeđe -> sivo -> snijeg.
    if land.any():
        e_max = e[land].max()
        height = np.clip(e[land] / e_max, 0.0, 1.0) if e_max > 0 else np.zeros(land.sum())
        h_stops = [0.0, 0.18, 0.42, 0.62, 0.82, 0.93, 1.0]
        out[land, 0] = np.interp(height, h_stops, [ 58,  98, 172, 138, 120, 190, 246])
        out[land, 1] = np.interp(height, h_stops, [128, 158, 156,  98, 112, 188, 246])
        out[land, 2] = np.interp(height, h_stops, [ 68,  82, 104,  64, 104, 196, 250])

    return out


class GPSSimulator:
    def __init__(self):
        pv.set_plot_theme("dark")
        self.plotter = pv.Plotter(title="GPS Simulator 3D", window_size=[WIN_W, WIN_H])
        # Dubok "svemirski" gradijent umjesto plosnate crne
        self.plotter.set_background((0.015, 0.03, 0.06), top=(0.0, 0.0, 0.0))

        self.constellation = WalkerDeltaConstellation()
        self.receiver = Receiver()
        self.start_time = time.time()
        self.time_scale = 100.0

        self.gt_pos = None
        self.calc_pos = None
        self.marker_radius = 60000

        self._setup_scene()
        self._setup_hud()

        # Klik na globus postavlja prijemnik (vraća točnu točku na površini)
        self.plotter.enable_point_picking(callback=self.on_click, show_message=False, left_clicking=True)

        # Tipkovnički prekidači
        self.use_dms = False
        self.plotter.add_key_event("d", self.toggle_dms)
        self.plotter.add_key_event("D", self.toggle_dms)
        self.kinematic_mode = False
        self.plotter.add_key_event("m", self.toggle_kinematic)
        self.plotter.add_key_event("M", self.toggle_kinematic)
        self.kinematic_velocity = np.array([100.0, 50.0, 0.0])  # [m/s]
        self.plotter.add_key_event("t", self.toggle_texture)
        self.plotter.add_key_event("T", self.toggle_texture)

    def toggle_dms(self):
        self.use_dms = not self.use_dms

    def toggle_kinematic(self):
        self.kinematic_mode = not self.kinematic_mode

    def toggle_texture(self):
        if self.earth_tex_actor is None:
            return
        self.show_texture = not self.show_texture
        self.earth_tex_actor.SetVisibility(self.show_texture)
        self.earth_actor.SetVisibility(not self.show_texture)
        self.earth_tex_actor.SetPickable(self.show_texture)
        self.earth_actor.SetPickable(not self.show_texture)

    # ---------------------------------------------------------------- scena ---
    def _setup_scene(self):
        self._add_starfield()

        # WGS-84 elipsoid s proceduralnim terenom.
        # Koristimo icosphere (geodezijska sfera) umjesto UV-sfere: trokuti su
        # ravnomjerni pa nema stapanja meridijana u polovima (bez "štipanja"/pruga).
        # Svaki smjer preslikamo na elipsoid preko lla_to_ecef s visinom terena,
        # pa je geometrija geodetski konzistentna: klik vraća visinu ≈ teren.
        sphere = pv.Icosphere(radius=R_EARTH, nsub=6)
        dirs = sphere.points / np.linalg.norm(sphere.points, axis=1)[:, np.newaxis]
        lats = np.degrees(np.arcsin(np.clip(dirs[:, 2], -1.0, 1.0)))
        lons = np.degrees(np.arctan2(dirs[:, 1], dirs[:, 0]))
        elevations = np.array([calculate_terrain_elevation(la, lo)
                               for la, lo in zip(lats, lons)])
        sphere.points = np.array([lla_to_ecef(la, lo, h)
                                  for la, lo, h in zip(lats, lons, elevations)])

        # Per-vertex RGB reljef (izbjegava cmap/lookup-table shader koji je pucao)
        sphere["relief"] = terrain_colors(elevations)
        self.earth_actor = self.plotter.add_mesh(
            sphere, scalars="relief", rgb=True, name="earth",
            pickable=True, lighting=True, smooth_shading=True,
            ambient=0.28, diffuse=0.85, specular=0.12, specular_power=12,
            show_scalar_bar=False,
        )

        # Opcionalna stvarna tekstura kontinenata (NASA Blue Marble, javna domena).
        # Prekidač 'T' prebacuje između hipsometrijskog reljefa i satelitske slike.
        # Ista geometrija: teren je geometrijski podpikselno malen pa tekstura
        # izgleda kao prava Zemlja (lon=0 u sredini slike -> poklapa se s meridijanom).
        self.earth_tex_actor = None
        self.show_texture = False
        tex_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "earth_texture.jpg")
        if os.path.exists(tex_path):
            try:
                # prevent_seam=False -> u wrapa kontinuirano 0..1 oko punih 360°;
                # default True mapira samo pola sfere pa zrcali teksturu.
                sphere.texture_map_to_sphere(inplace=True, prevent_seam=False)
                tex = pv.read_texture(tex_path)
                self.earth_tex_actor = self.plotter.add_mesh(
                    sphere, texture=tex, name="earth_tex", pickable=False,
                    lighting=True, smooth_shading=True, ambient=0.30, diffuse=0.9,
                    specular=0.10, specular_power=10, show_scalar_bar=False)
                self.earth_tex_actor.SetVisibility(False)
            except Exception:
                self.earth_tex_actor = None

        # Atmosferski halo: prozirna sfera, prednje plohe skrivene -> rub-glow
        atmo = pv.Sphere(radius=R_EARTH * 1.025, theta_resolution=90, phi_resolution=90)
        self.plotter.add_mesh(atmo, color=(0.30, 0.62, 1.0), opacity=0.12,
                              name="atmo", lighting=False, pickable=False,
                              culling="front", show_scalar_bar=False)

        self._add_graticule()

        # Sunčevo svjetlo za plastičnost reljefa
        sun = pv.Light(position=(3, -2, 2), focal_point=(0, 0, 0),
                       color="white", intensity=0.9, light_type="scene light")
        self.plotter.add_light(sun)

        # Markeri: istina (amber) i EKF procjena (cyan)
        gt_sphere = pv.Sphere(radius=self.marker_radius, theta_resolution=16, phi_resolution=16)
        calc_sphere = pv.Sphere(radius=self.marker_radius, theta_resolution=16, phi_resolution=16)
        self.plotter.add_mesh(gt_sphere, color=C_AMBER, name="gt_marker",
                              lighting=False, pickable=False, show_scalar_bar=False)
        self.plotter.add_mesh(calc_sphere, color=C_CYAN, name="calc_marker",
                              lighting=False, pickable=False, show_scalar_bar=False)
        self.plotter.actors["gt_marker"].SetVisibility(False)
        self.plotter.actors["calc_marker"].SetVisibility(False)

        # Orbitni prstenovi (6 ravnina) — inercijalna geometrija, svaki frame se
        # zarotira za Zemljin kut pa se poklapaju s trenutnim ECEF položajima satelita.
        self._add_orbit_rings()

        # Sateliti
        sat_geom = pv.Sphere(radius=180000, theta_resolution=10, phi_resolution=10)
        for sat in self.constellation.satellites:
            self.plotter.add_mesh(sat_geom, color=(0.4, 0.45, 0.55), name=sat.sat_id,
                                  lighting=False, pickable=False, show_scalar_bar=False)

        # Signalne zrake prijemnik -> praćeni sateliti (dinamički se osvježavaju)
        self.ray_mesh = pv.PolyData()
        self.ray_mesh.points = np.zeros((2, 3))
        self.ray_mesh.lines = np.array([2, 0, 1])
        self.ray_actor = self.plotter.add_mesh(
            self.ray_mesh, color=C_GREEN, line_width=1, opacity=0.35,
            lighting=False, pickable=False, show_scalar_bar=False)
        self.ray_actor.SetVisibility(False)

    def _add_orbit_rings(self):
        self.orbit_actors = []
        a, e = self.constellation.a, self.constellation.e
        inc, w = np.radians(self.constellation.i), np.radians(self.constellation.w)
        E = np.linspace(0.0, 2.0 * np.pi, 160)
        x_orb = a * (np.cos(E) - e)
        y_orb = a * np.sqrt(1.0 - e**2) * np.sin(E)
        # Rz(w) -> Rx(inc) -> Rz(lan), isti redoslijed kao calculate_orbital_position
        x1 = x_orb * np.cos(w) - y_orb * np.sin(w)
        y1 = x_orb * np.sin(w) + y_orb * np.cos(w)
        x2, y2, z2 = x1, y1 * np.cos(inc), y1 * np.sin(inc)
        for lan_deg in sorted({s.lan for s in self.constellation.satellites}):
            lan = np.radians(lan_deg)
            X = x2 * np.cos(lan) - y2 * np.sin(lan)
            Y = x2 * np.sin(lan) + y2 * np.cos(lan)
            pts = np.column_stack([X, Y, z2])
            actor = self.plotter.add_mesh(pv.MultipleLines(points=pts), color=C_CYAN,
                                          line_width=1, opacity=0.16, lighting=False,
                                          pickable=False, show_scalar_bar=False)
            self.orbit_actors.append(actor)

    def _update_rays(self, sat_positions):
        if self.gt_pos is None or not sat_positions:
            self.ray_actor.SetVisibility(False)
            return
        n = len(sat_positions)
        pts = np.empty((2 * n, 3))
        pts[0::2] = self.gt_pos
        pts[1::2] = np.asarray(sat_positions)
        conn = np.empty((n, 3), dtype=np.int64)
        conn[:, 0] = 2
        conn[:, 1] = np.arange(0, 2 * n, 2)
        conn[:, 2] = np.arange(1, 2 * n, 2)
        self.ray_mesh.points = pts
        self.ray_mesh.lines = conn.ravel()
        self.ray_mesh.Modified()
        self.ray_actor.SetVisibility(True)

    def _add_starfield(self):
        rng = np.random.default_rng(42)
        d = rng.normal(size=(900, 3))
        d /= np.linalg.norm(d, axis=1)[:, np.newaxis]
        stars = pv.PolyData(d * R_EARTH * 30.0)
        self.plotter.add_mesh(stars, color="white", point_size=1.6, opacity=0.75,
                              lighting=False, pickable=False, render_points_as_spheres=True,
                              show_scalar_bar=False)

    def _add_graticule(self):
        """Tanka mreža meridijana i paralela + istaknuti ekvator i nulti meridijan."""
        alt = 15000.0
        for lon in range(-150, 181, 30):
            pts = np.array([lla_to_ecef(la, lon, alt) for la in np.linspace(-88, 88, 60)])
            hot = (lon == 0)
            self.plotter.add_mesh(pv.MultipleLines(points=pts),
                                  color=C_AMBER if hot else C_CYAN,
                                  line_width=2 if hot else 1,
                                  opacity=0.5 if hot else 0.16,
                                  lighting=False, pickable=False, show_scalar_bar=False)
        for lat in range(-60, 61, 30):
            pts = np.array([lla_to_ecef(lat, lo, alt) for lo in np.linspace(-180, 180, 120)])
            hot = (lat == 0)
            self.plotter.add_mesh(pv.MultipleLines(points=pts),
                                  color=C_AMBER if hot else C_CYAN,
                                  line_width=2 if hot else 1,
                                  opacity=0.5 if hot else 0.16,
                                  lighting=False, pickable=False, show_scalar_bar=False)

    # ------------------------------------------------------------------ HUD ---
    def _panel(self, actor, color, size=15, bold=False, mono=True, bg=True):
        tp = actor.GetTextProperty()
        tp.SetColor(*color)
        tp.SetFontSize(size)
        tp.SetFontFamilyToCourier() if mono else tp.SetFontFamilyToArial()
        tp.SetBold(1 if bold else 0)
        tp.SetLineSpacing(1.25)
        tp.SetVerticalJustificationToTop()
        if bg:
            tp.SetBackgroundColor(*C_PANEL)
            tp.SetBackgroundOpacity(0.62)
            tp.SetFrame(1)
            tp.SetFrameColor(color[0] * 0.5, color[1] * 0.5, color[2] * 0.5)
            tp.SetFrameWidth(1)
        return actor

    def _setup_hud(self):
        H = WIN_H
        # Naslov + podnaslov (bez panela, sa sjenom)
        t = self.plotter.add_text("GPS SIMULATOR 3D", position=(28, H - 40),
                                  font_size=22, color=C_CYAN, shadow=True, name="title")
        self._panel(t, C_CYAN, size=24, bold=True, mono=False, bg=False)
        s = self.plotter.add_text("GNSS constellation  ·  EKF  ·  RAIM integrity",
                                  position=(28, H - 70), font_size=11, color=C_DIM, name="subtitle")
        self._panel(s, C_DIM, size=12, mono=False, bg=False)

        # Kontrole
        ctl = self.plotter.add_text(
            " CLICK   postavi prijemnik\n [ D ]   DMS format\n [ M ]   kinematicki nacin\n [ T ]   tekstura / reljef",
            position=(28, H - 108), font_size=13, color=C_TEXT, name="controls")
        self._panel(ctl, C_TEXT, size=13)

        # Telemetrija (gore desno)
        self.txt_tel = self.plotter.add_text("", position=(WIN_W - 300, H - 40),
                                             font_size=14, color=C_GREEN, name="telemetry")
        self._panel(self.txt_tel, C_GREEN, size=14)

        # Status / koordinate (dolje lijevo)
        self.txt_status = self.plotter.add_text("", position=(28, 190),
                                                font_size=14, color=C_TEXT, name="status")
        self._panel(self.txt_status, C_TEXT, size=14)

        # RAIM alarm (iznad statusa, crveni, skriva se kad nema alarma)
        self.txt_raim = self.plotter.add_text("", position=(28, 250),
                                              font_size=15, color=C_RED, name="raim")
        self._panel(self.txt_raim, C_RED, size=15, bold=True)
        self.txt_raim.SetVisibility(False)

        self._set_idle_hud()

    def _set_idle_hud(self):
        self.txt_status.SetInput(" NO FIX\n klikni na globus za\n postavljanje prijemnika")
        self.txt_tel.SetInput(" TELEMETRY\n ---------\n waiting for fix...")

    # ---------------------------------------------------------------- klik ----
    def on_click(self, point):
        if point is None:
            return
        # Klik prihvaćamo geodetski: točka mora biti blizu površine elipsoida.
        _, _, click_alt = ecef_to_lla(point[0], point[1], point[2])
        if abs(click_alt) > 20000:
            return

        self.gt_pos = np.array(point)
        gt_actor = self.plotter.actors.get("gt_marker")
        if gt_actor:
            gt_actor.SetVisibility(True)
            gt_actor.position = self.gt_pos

        self.receiver.set_position(self.gt_pos)
        self.receiver.reset()  # pozicija se drastično promijenila -> restart EKF-a

    # ----------------------------------------------------------- formatiranje -
    def _coord_line(self, label, lat, lon, alt):
        if self.use_dms:
            return f" {label:<6} {format_dms(lat, True)}  {format_dms(lon, False)}  {alt:.0f} m"
        return f" {label:<6} Lat {lat:8.3f}  Lon {lon:8.3f}  Alt {alt:6.0f} m"

    # ----------------------------------------------------------------- run ----
    def _frame_camera(self):
        d = R_EARTH * 3.4
        self.plotter.camera_position = [(d * 0.95, -d * 0.85, d * 0.55), (0, 0, 0), (0, 0, 1)]

    def run(self):
        self.plotter.show(interactive_update=True, auto_close=False)
        self._frame_camera()

        try:
            while not getattr(self.plotter, "_closed", False):
                if getattr(self.plotter, "ren_win", None) is None:
                    break

                curr_sim_time = (time.time() - self.start_time) * self.time_scale
                positions = self.constellation.update_all(curr_sim_time)
                signals = self.receiver.receive_signals(self.constellation, curr_sim_time)
                visible_ids = [s["sat_id"] for s in signals]

                for sat_id, pos in positions.items():
                    actor = self.plotter.actors.get(sat_id)
                    if actor:
                        actor.position = pos
                        actor.GetProperty().SetColor(*(C_GREEN if sat_id in visible_ids else (0.34, 0.39, 0.5)))

                # Orbitni prstenovi prate Zemljinu rotaciju (ECEF = Rz(-theta) * inercijalno)
                theta_deg = np.degrees(OMEGA_E * curr_sim_time)
                for ring in self.orbit_actors:
                    ring.orientation = (0.0, 0.0, -theta_deg)

                if self.gt_pos is not None:
                    if self.kinematic_mode:
                        dt_sim = 0.02 * self.time_scale
                        self.gt_pos = self.gt_pos + self.kinematic_velocity * dt_sim
                        lat, lon, _ = ecef_to_lla(self.gt_pos[0], self.gt_pos[1], self.gt_pos[2])
                        h = calculate_terrain_elevation(lat, lon)
                        self.gt_pos = np.array(lla_to_ecef(lat, lon, h + 500.0))
                        self.receiver.set_position(self.gt_pos)
                        gt_actor = self.plotter.actors.get("gt_marker")
                        if gt_actor:
                            gt_actor.position = self.gt_pos

                    # Signalne zrake do praćenih satelita
                    self._update_rays([s["sat_pos"] for s in signals])

                    self.calc_pos, dop = self.receiver.solve_position()
                    if self.calc_pos is not None:
                        calc_actor = self.plotter.actors.get("calc_marker")
                        if calc_actor:
                            calc_actor.SetVisibility(True)
                            calc_actor.position = self.calc_pos

                        glat, glon, galt = ecef_to_lla(*self.gt_pos)
                        clat, clon, calt = ecef_to_lla(*self.calc_pos)
                        error = float(np.linalg.norm(self.calc_pos - self.gt_pos))
                        truth_label = "FLYING" if self.kinematic_mode else "TRUTH"
                        state = "TRACKING" if self.kinematic_mode else "FIX ACQUIRED"
                        self.txt_status.SetInput(
                            f" {state}\n"
                            f"{self._coord_line(truth_label, glat, glon, galt)}\n"
                            f"{self._coord_line('EST', clat, clon, calt)}\n"
                            f" ERROR  {error:6.1f} m"
                        )

                        sats_num = len(visible_ids)
                        gdop_str = f"{dop:6.2f}" if dop is not None else "   N/A"
                        vel = np.linalg.norm(self.receiver.x_ekf[3:6]) if self.receiver.ekf_initialized else 0.0
                        clk_us = self.receiver.clock_bias * 1e6
                        self.txt_tel.SetInput(
                            " TELEMETRY\n"
                            " ---------\n"
                            f" SATS   {sats_num:>2d} / {len(self.constellation.satellites)}\n"
                            f" GDOP   {gdop_str}\n"
                            f" VEL    {vel:6.2f} m/s\n"
                            f" CLK    {clk_us:7.1f} us"
                        )

                        raim = getattr(self.receiver, "raim_alarm", "")
                        if raim:
                            self.txt_raim.SetInput(f" ! {raim}")
                            self.txt_raim.SetVisibility(True)
                        else:
                            self.txt_raim.SetVisibility(False)
                    else:
                        self.txt_status.SetInput(" EKF LOST\n premalo satelita ili\n RAIM odbacio sve")
                        self.txt_tel.SetInput(" TELEMETRY\n ---------\n no solution")
                        raim = getattr(self.receiver, "raim_alarm", "")
                        self.txt_raim.SetVisibility(bool(raim))
                        if raim:
                            self.txt_raim.SetInput(f" ! {raim}")

                if getattr(self.plotter, "_closed", False):
                    break

                self.plotter.update()
                time.sleep(0.02)
        except Exception:
            pass
        finally:
            pass


if __name__ == "__main__":
    import vtk
    # Isključujemo C++ VTK upozorenja pri izlasku (PyVista gubi OpenGL kontekst)
    vtk.vtkObject.GlobalWarningDisplayOff()
    vtk.vtkLogger.SetStderrVerbosity(vtk.vtkLogger.VERBOSITY_OFF)
    sim = GPSSimulator()
    sim.run()
