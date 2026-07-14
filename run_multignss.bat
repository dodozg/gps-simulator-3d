@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  multi-GNSS pozicioniranje (headless)
REM  GPS+Galileo+GLONASS+BeiDou: dostupnost, PDOP, inter-system bias.
REM  Primjer:  run_multignss.bat --lat 1.35 --lon 103.8 --mask 30
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0multignss.py" %*

echo.
pause
endlocal
