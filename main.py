import pyvista as pv
import numpy as np
import time
from satellite import WalkerDeltaConstellation
from receiver import Receiver
from physics_engine import R_EARTH, calculate_terrain_elevation
from utils import ecef_to_lla, lla_to_ecef, format_dms

class GPSSimulator:
    def __init__(self):
        # Postavljanje teme koja je često stabilnija
        pv.set_plot_theme("document")
        self.plotter = pv.Plotter(title="GPS Simulator 3D - Realistic Terrain")
        self.plotter.set_background("black")
        
        self.constellation = WalkerDeltaConstellation()
        self.receiver = Receiver()
        self.start_time = time.time()
        self.time_scale = 100.0
        
        self.gt_pos = None
        self.calc_pos = None
        self.marker_radius = 50000 
        
        self._setup_scene()
        
        # Point picking vraća točnu koordinatu na površini
        self.plotter.enable_point_picking(callback=self.on_click, show_message=False, left_clicking=True)
        
        # DMS Toggle
        self.use_dms = False
        self.plotter.add_key_event("d", self.toggle_dms)
        self.plotter.add_key_event("D", self.toggle_dms)
        
        # Kinematic Mode Toggle
        self.kinematic_mode = False
        self.plotter.add_key_event("m", self.toggle_kinematic)
        self.plotter.add_key_event("M", self.toggle_kinematic)
        self.kinematic_velocity = np.array([100.0, 50.0, 0.0]) # Brzina [m/s]
        
        self.plotter.add_text("GPS Simulator 3D\nCLICK ON EARTH\n'D' - Toggle D.M.S\n'M' - Toggle Kinematic", position='upper_left', font_size=10, color="cyan", name="info_text")

    def toggle_dms(self):
        self.use_dms = not self.use_dms
        
    def toggle_kinematic(self):
        self.kinematic_mode = not self.kinematic_mode

    def _setup_scene(self):
        # WGS-84 elipsoid s proceduralnim terenom.
        # Krećemo od jedinične sfere (samo smjerovi), pa svaki smjer preslikamo na
        # elipsoid preko lla_to_ecef s pripadnom visinom terena. Time je geometrija
        # globusa geodetski konzistentna s ostatkom sustava: klik na površinu vraća
        # visinu ≈ teren (a ne ~14 km greške koju bi dala sferna aproksimacija).
        sphere = pv.Sphere(radius=R_EARTH, theta_resolution=150, phi_resolution=150)
        dirs = sphere.points / np.linalg.norm(sphere.points, axis=1)[:, np.newaxis]
        lats = np.degrees(np.arcsin(np.clip(dirs[:, 2], -1.0, 1.0)))
        lons = np.degrees(np.arctan2(dirs[:, 1], dirs[:, 0]))

        elevations = np.array([calculate_terrain_elevation(la, lo)
                               for la, lo in zip(lats, lons)])
        sphere.points = np.array([lla_to_ecef(la, lo, h)
                                  for la, lo, h in zip(lats, lons, elevations)])

        # Uklonili smo scalars="Elevation" i cmap="terrain" zbog pogreške s OpenGL shaderima
        # Zemlja će sada biti jednobojna, ali teren i dalje ostaje fizički točan
        self.earth_actor = self.plotter.add_mesh(
            sphere, 
            color="blue", # Jednostavna boja umjesto složene teksture
            name="earth", 
            pickable=True, 
            lighting=True, 
            show_scalar_bar=False
        )
        
        # Prime Meridian
        pm_points = [lla_to_ecef(lat, 0, 0) for lat in np.linspace(-90, 90, 100)]
        self.plotter.add_mesh(pv.MultipleLines(points=np.array(pm_points)), color="red", line_width=3, lighting=False)

        # Inicijalni skriveni markeri
        gt_sphere = pv.Sphere(radius=self.marker_radius, center=(0,0,0), theta_resolution=12, phi_resolution=12)
        calc_sphere = pv.Sphere(radius=self.marker_radius, center=(0,0,0), theta_resolution=12, phi_resolution=12)
        
        self.plotter.add_mesh(gt_sphere, color="red", name="gt_marker", lighting=False)
        self.plotter.add_mesh(calc_sphere, color="white", name="calc_marker", lighting=False)
        
        self.plotter.actors["gt_marker"].SetVisibility(False)
        self.plotter.actors["calc_marker"].SetVisibility(False)
        
        # Inicijalizacija tekstualnih aktora s pixel koordinatama kako bi postali vtkTextActor (ima SetInput) umjesto CornerAnnotation
        self.txt_gt = self.plotter.add_text("", position=(10, 10), font_size=10, color="red", name="gt_coord")
        self.txt_calc = self.plotter.add_text("", position=(10, 40), font_size=10, color="white", name="calc_coord")
        self.txt_err = self.plotter.add_text("", name="err_text", position=(10, 70), font_size=12, color="orange")
        self.txt_verbose = self.plotter.add_text("", name="verbose_text", position=(700, 550), font_size=9, color="lightgreen")
        self.txt_raim = self.plotter.add_text("", name="raim_text", position=(10, 100), font_size=12, color="red")
        
        sat_geom = pv.Sphere(radius=200000, theta_resolution=8, phi_resolution=8)
        for sat in self.constellation.satellites:
            self.plotter.add_mesh(sat_geom, color="yellow", name=sat.sat_id, lighting=False)

    def on_click(self, point):
        if point is None: return
        # Klik prihvaćamo geodetski: točka mora biti blizu površine elipsoida.
        # Teren je u rasponu ~ -11..+9 km, pa ±20 km sigurno obuhvaća površinu,
        # a odbacuje slučajne pogotke satelita (na ~20 000 km visine).
        _, _, click_alt = ecef_to_lla(point[0], point[1], point[2])
        if abs(click_alt) > 20000: return

        # Koristimo točno mjesto klika na terenu (ECEF).
        self.gt_pos = np.array(point)
        
        gt_actor = self.plotter.actors.get("gt_marker")
        if gt_actor:
            gt_actor.SetVisibility(True)
            gt_actor.position = self.gt_pos
            
        self.receiver.set_position(self.gt_pos)
        self.receiver.reset() # Restartiraj EKF pošto se pozicija drastično promijenila
        
        lat, lon, alt = ecef_to_lla(self.gt_pos[0], self.gt_pos[1], self.gt_pos[2])
        if self.use_dms:
            coord_str = f"Lat: {format_dms(lat, True)}, Lon: {format_dms(lon, False)}, Alt: {alt:.1f}m"
        else:
            coord_str = f"Lat: {lat:7.3f}, Lon: {lon:7.3f}, Alt: {alt:.1f}m"
        self.txt_gt.SetInput(f"CLICKED (RED): {coord_str}")

    def run(self):
        # Koristimo interactive_update=True koji radi najbolje za stalne simulacije
        self.plotter.show(interactive_update=True, auto_close=False)
        
        try:
            # Petlja radi sve dok korisnik ne zatvori prozor (plotter._closed postaje True)
            while not getattr(self.plotter, '_closed', False):
                # Prije svakog koraka dodatno provjeravamo postoji li još render window
                if getattr(self.plotter, 'ren_win', None) is None:
                    break
                    
                curr_sim_time = (time.time() - self.start_time) * self.time_scale
                positions = self.constellation.update_all(curr_sim_time)
                signals = self.receiver.receive_signals(self.constellation, curr_sim_time)
                visible_ids = [s['sat_id'] for s in signals]
                
                for sat_id, pos in positions.items():
                    actor = self.plotter.actors.get(sat_id)
                    if actor:
                        actor.position = pos
                        color = "lime" if sat_id in visible_ids else "yellow"
                        actor.GetProperty().SetColor(pv.Color(color).float_rgb)
                
                if self.gt_pos is not None:
                    # KINEMATIC MODE (Pomicanje prijemnika)
                    if self.kinematic_mode:
                        # Skalirano simulacijsko vrijeme
                        dt_sim = 0.02 * self.time_scale 
                        self.gt_pos += self.kinematic_velocity * dt_sim
                        
                        # Zadrži ga iznad terena (Avionski let 500m iznad zemlje)
                        lat, lon, _ = ecef_to_lla(self.gt_pos[0], self.gt_pos[1], self.gt_pos[2])
                        h = calculate_terrain_elevation(lat, lon)
                        self.gt_pos = np.array(lla_to_ecef(lat, lon, h + 500.0))
                        
                        self.receiver.set_position(self.gt_pos)
                        
                        # Osvježi crveni marker
                        gt_actor = self.plotter.actors.get("gt_marker")
                        if gt_actor:
                            gt_actor.position = self.gt_pos
                        
                        # Ažuriraj tekst
                        if self.use_dms:
                            coord_str = f"Lat: {format_dms(lat, True)}, Lon: {format_dms(lon, False)}, Alt: {h+500.0:.1f}m"
                        else:
                            coord_str = f"Lat: {lat:7.3f}, Lon: {lon:7.3f}, Alt: {h+500.0:.1f}m"
                        self.txt_gt.SetInput(f"FLYING (RED): {coord_str}")

                    self.calc_pos, dop = self.receiver.solve_position()
                    if self.calc_pos is not None:
                        calc_actor = self.plotter.actors.get("calc_marker")
                        if calc_actor:
                            calc_actor.SetVisibility(True)
                            calc_actor.position = self.calc_pos
                        
                        lat, lon, alt = ecef_to_lla(self.calc_pos[0], self.calc_pos[1], self.calc_pos[2])
                        if self.use_dms:
                            calc_str = f"Lat: {format_dms(lat, True)}, Lon: {format_dms(lon, False)}, Alt: {alt:.1f}m"
                        else:
                            calc_str = f"Lat: {lat:7.3f}, Lon: {lon:7.3f}, Alt: {alt:.1f}m"
                        
                        self.txt_calc.SetInput(f"CALC (WHITE): {calc_str}")
                        
                        error = np.linalg.norm(self.calc_pos - self.gt_pos)
                        self.txt_err.SetInput(f"Error: {error:.1f} m")
                        
                        # VERBOSE OUTFIT
                        sats_num = len(visible_ids)
                        gdop_str = f"{dop:.2f}" if dop is not None else "N/A"
                        vel = np.linalg.norm(self.receiver.x_ekf[3:6]) if self.receiver.ekf_initialized else 0.0
                        clk_bias_us = self.receiver.clock_bias * 1e6
                        
                        verbose_info = (
                            f"--- VERBOSE EKF DATA ---\n"
                            f"Satellites Tracked: {sats_num}\n"
                            f"GDOP: {gdop_str}\n"
                            f"EKF Velocity: {vel:.2f} m/s\n"
                            f"Clock Bias: {clk_bias_us:.2f} us\n"
                            f"------------------------"
                        )
                        self.txt_verbose.SetInput(verbose_info)
                        
                        # RAIM Alarm Display
                        if hasattr(self.receiver, 'raim_alarm') and self.receiver.raim_alarm != "":
                            self.txt_raim.SetInput(self.receiver.raim_alarm)
                        else:
                            self.txt_raim.SetInput("")
                    else:
                        self.txt_verbose.SetInput("--- EKF LOST ---\nNot enough satellites\nor RAIM rejected all.")
                        self.txt_calc.SetInput("")
                        self.txt_err.SetInput("")
                        if hasattr(self.receiver, 'raim_alarm') and self.receiver.raim_alarm != "":
                            self.txt_raim.SetInput(self.receiver.raim_alarm)
                
                # Sigurnosna provjera prije renderiranja
                if getattr(self.plotter, '_closed', False):
                    break
                    
                self.plotter.update()
                time.sleep(0.02)
        except Exception:
            pass
        finally:
            # Nećemo zvati plotter.close() ako ga je korisnik već zatvorio kroz UI (to uzrokuje C++ shader error)
            pass

if __name__ == "__main__":
    import vtk
    # Isključujemo C++ VTK Upozorenja u konzoli pri izlasku jer PyVista gubi OpenGL kontekst 
    vtk.vtkObject.GlobalWarningDisplayOff()
    vtk.vtkLogger.SetStderrVerbosity(vtk.vtkLogger.VERBOSITY_OFF)
    sim = GPSSimulator()
    sim.run()
