import numpy as np

C = 299792458.0 # m/s
R_EARTH = 6371000.0 # m
MU = 3.986004418e14 # m^3/s^2
J2 = 1.08262668e-3 # Earth's J2 perturbation coefficient

def calculate_terrain_elevation(lat, lon):
    """Visina terena [m] na (lat, lon). Delegira na `terrain` modul (pravi DEM).

    Prije je ovo bila čista suma sinusa koja je posvuda stvarala lažne planine do
    ~9 km i blokirala vidljivost satelita (npr. Tokio -> 0 satelita). Sada koristi
    stvarni globalni DEM (NASA SRTM) uz proceduralni fallback. Vidi `terrain.py`.
    """
    import terrain
    return terrain.elevation(lat, lon)

def get_orbital_period(a):
    """
    Vraća orbitalni period (u sekundama) za veliku poluos 'a' prema
    trećem Keplerovom zakonu: T = 2*pi*sqrt(a^3 / mu).
    Za GPS visinu (a ~ 26.560 km) rezultat je ~11.97 sati.
    """
    return 2.0 * np.pi * np.sqrt(a**3 / MU)

def calculate_orbital_position(a, e, i, lan, w, m0, t):
    """
    Kalkulira poziciju satelita koristeći Keplerove elemente.
    Uključuje Newton-Raphson za Keplerovu jednadžbu i J2 precesiju.
    Vraća (poziciju_ecef, E_anomaliju).
    """
    n = np.sqrt(MU / a**3)
    M = m0 + n * t
    
    # Newton-Raphson za Keplerovu jednadžbu
    E = M
    if e > 1e-5:
        for _ in range(10):
            E_new = E - (E - e * np.sin(E) - M) / (1.0 - e * np.cos(E))
            if abs(E_new - E) < 1e-8:
                E = E_new
                break
            E = E_new
    
    # Pozicija u orbitalnoj ravnini
    x_orb = a * (np.cos(E) - e)
    y_orb = a * np.sqrt(1 - e**2) * np.sin(E)
    
    inc_rad = np.radians(i)
    w_rad = np.radians(w)
    
    # J2 Perturbacija: Rektascenzija uzlaznog čvora (LAN) precesira
    lan_dot = -1.5 * n * J2 * (R_EARTH / a)**2 * np.cos(inc_rad)
    omega = np.radians(lan + np.degrees(lan_dot * t))
    
    # J2 Perturbacija: Argument perigeja (w) precesira
    w_dot = 0.75 * n * J2 * (R_EARTH / a)**2 * (4 - 5*np.sin(inc_rad)**2)
    w_current = w_rad + w_dot * t
    
    # Rotacija: Rz(omega) * Rx(inc) * Rz(w_current)
    # 1. Rz(w_current)
    x1 = x_orb * np.cos(w_current) - y_orb * np.sin(w_current)
    y1 = x_orb * np.sin(w_current) + y_orb * np.cos(w_current)
    z1 = 0.0
    
    # 2. Rx(inc)
    x2 = x1
    y2 = y1 * np.cos(inc_rad)
    z2 = y1 * np.sin(inc_rad)
    
    # 3. Rz(omega)
    x = x2 * np.cos(omega) - y2 * np.sin(omega)
    y = x2 * np.sin(omega) + y2 * np.cos(omega)
    z = z2
    
    # Zemljina rotacija (ECEF transformacija)
    omega_e = 7.2921159e-5 # rad/s
    theta = omega_e * t
    
    x_ecef = x * np.cos(theta) + y * np.sin(theta)
    y_ecef = -x * np.sin(theta) + y * np.cos(theta)
    z_ecef = z
    
    return np.array([x_ecef, y_ecef, z_ecef]), E

def get_dynamic_relativistic_offset(a, e, E):
    """
    Dinamička relativistička korekcija uslijed ekscentriciteta orbite.
    Ovisi o trenutnoj ekscentričnoj anomaliji E.
    """
    return (-2.0 * np.sqrt(MU * a) / C**2) * e * np.sin(E)

def get_relativistic_drift_rate(a):
    """
    Kombinirana specijalna i opća teorija relativnosti.
    Satovi na satelitima kucaju brže za ~38 mikrosekundi dnevno.
    """
    return 4.46e-10 # Ogruba aproksimacija drift rate-a (sec/sec)

def calculate_ionospheric_delay(sat_pos, receiver_pos, frequency_hz=1575.42e6):
    """
    Jednostavan model ionosferskog kašnjenja ovisno o elevaciji i frekvenciji.
    Kašnjenje je obrnuto proporcionalno kvadratu frekvencije.
    Vraća kašnjenje u metrima.
    """
    # Vektor od prijemnika do satelita
    vec = sat_pos - receiver_pos
    dist = np.linalg.norm(vec)
    
    if dist == 0:
        return 0.0
        
    # Jedinični vektori
    vec_dir = vec / dist
    rec_dir = receiver_pos / np.linalg.norm(receiver_pos)
    
    # Elevacijski kut (sin(elev) = dot product lokalnog zenita i smjera signala)
    sin_elev = np.dot(rec_dir, vec_dir)
    
    if sin_elev < 0.05: # Manje od ~3 stupnja
        sin_elev = 0.05
        
    # Zenitno kašnjenje je otprilike 5 do 15 metara za L1 frekvenciju
    f_l1 = 1575.42e6
    base_zenith_delay = 7.0 
    zenith_delay_meters = base_zenith_delay * ((f_l1 / frequency_hz)**2)
    
    # Mapping funkcija: 1 / sin(elev) aproksimira kosi put kroz sloj
    delay = zenith_delay_meters / sin_elev
    return delay

def calculate_sagnac_correction(sat_pos, receiver_pos):
    """
    Korekcija Sagnac efekta (rotacija Zemlje tijekom putovanja signala).
    Vraća korekciju u metrima koja se treba dodati modelu.
    """
    omega_e = 7.2921159e-5 # rad/s rotacija Zemlje
    # Standardna aproksimacija Sagnac efekta
    correction = (omega_e / C) * (sat_pos[0] * receiver_pos[1] - sat_pos[1] * receiver_pos[0])
    return correction

def simulate_clock_noise(dt, current_bias, current_drift, h0, h2, rng=None):
    """
    Simulira ponašanje realnog oscilatora (kvarc ili rubidij) koristeći Allanovu varijancu.
    h0: White frequency noise (slučajni hod faze)
    h2: Random walk frequency noise (slučajni hod frekvencije)
    rng: np.random.Generator za reproducibilnost (None -> svjež default_rng).
    """
    if rng is None:
        rng = np.random.default_rng()
    # White noise na frekvenciji (utječe na fazu/bias)
    w_freq = rng.normal(0, np.sqrt(h0 / 2.0))
    # Random walk na frekvenciji (utječe na drift)
    rw_freq = rng.normal(0, np.sqrt(2.0 * np.pi**2 * h2 * dt))
    
    new_drift = current_drift + rw_freq
    new_bias = current_bias + current_drift * dt + w_freq * np.sqrt(dt)
    
    return new_bias, new_drift

def generate_ephemeris_error(rng=None):
    """
    Simulira pogrešku efemerida u prenesenoj navigacijskoj poruci.
    Obično je to pogreška od par metara u 3D prostoru.
    rng: np.random.Generator za reproducibilnost (None -> svjež default_rng).
    Vraća 3D vektor pogreške (x, y, z) u metrima.
    """
    if rng is None:
        rng = np.random.default_rng()
    # Pogreška je oko 1-2 metra po osi za moderne GPS satelite
    return rng.normal(0, 1.5, size=3)

def calculate_tropospheric_delay(sat_pos, receiver_pos):
    """
    Pojednostavljeni Hopfield model za troposfersko kašnjenje.
    Troposfera nije ovisna o frekvenciji (za razliku od ionosfere).
    Kašnjenje u zenitu je obično oko 2.3 do 2.5 metara, a raste na manjim elevacijama.
    """
    vec = sat_pos - receiver_pos
    dist = np.linalg.norm(vec)
    
    if dist == 0:
        return 0.0
        
    vec_dir = vec / dist
    rec_dir = receiver_pos / np.linalg.norm(receiver_pos)
    
    sin_elev = np.dot(rec_dir, vec_dir)
    if sin_elev < 0.087: # Ispod ~5 stupnjeva se obično ignorira u prijemnicima
        sin_elev = 0.087
        
    # Zenith delay oko 2.4 m (suhi dio ~2.3m, vlažni dio ~0.1m)
    zenith_delay = 2.4
    
    # Jednostavna maping funkcija
    delay = zenith_delay / sin_elev
    return delay
