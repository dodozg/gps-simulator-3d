@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  3D simulator (PyVista / VTK GUI)
REM  Koristi .venv\Scripts\python.exe ako radi; inace sistemski
REM  Python + PYTHONPATH na .venv pakete (fallback za drugi stroj).
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

echo Pokrecem GPS Simulator 3D...
echo   CLICK postavi prijemnik  ^|  D=DMS  M=kinematika  T=tekstura/reljef
echo.
"%PY%" "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo [GRESKA] Simulator je zavrsio s greskom - vidi poruke iznad.
)
echo.
pause
endlocal
