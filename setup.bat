@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  ciscenje i ponovno kreiranje .venv-a
REM
REM  Pokreni ovo samo ako je .venv trajno pokvaren. Kreira svjez
REM  virtualni okolis i instalira sve ovisnosti (GUI + testovi).
REM  NAPOMENA: skida ~150 MB (pyvista/vtk/PyQt5), moze potrajati.
REM ============================================================
setlocal
cd /d "%~dp0"

echo Brisem stari .venv (ako postoji) i kreiram svjez...
python -m venv .venv --clear
if errorlevel 1 (
    echo [GRESKA] Ne mogu kreirati venv. Je li 'python' na PATH-u?
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements-viz.txt -r requirements-dev.txt
if errorlevel 1 (
    echo [GRESKA] Instalacija ovisnosti nije uspjela.
    pause
    exit /b 1
)

echo.
echo Gotovo. Pokreni run_simulator.bat.
pause
endlocal
