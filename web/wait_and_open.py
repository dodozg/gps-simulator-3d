"""Pričekaj da web server odgovori pa otvori preglednik.

Launcher (run_webapp.bat / .sh) ovo pokreće ODVOJENO (u pozadini) dok uvicorn ide
u prednjem planu. Prije se preglednik otvarao ODMAH, prije nego što je uvicorn
digao port, pa je tab prvo prijavio grešku ("nije moguće doći do stranice") i tek
se nakon par trenutaka osvježio. Ovdje pollamo HTTP root dok ne odgovori (status
< 500 = app poslužuje) pa tek onda otvorimo preglednik.

Uporaba:  python web/wait_and_open.py [PORT] [TIMEOUT_S]
"""
import sys
import time
import urllib.request
import webbrowser

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
url = f"http://127.0.0.1:{port}/"

deadline = time.time() + timeout_s
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as r:
            if r.status < 500:
                break
    except Exception:
        time.sleep(0.3)

# Otvori i ako je isteklo vrijeme — bolje otvoriti (možda server ipak diže) nego
# ostaviti korisnika bez ičega; u najgorem slučaju je ponašanje kao i prije.
webbrowser.open(url)
