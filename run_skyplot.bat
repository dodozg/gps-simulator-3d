@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  skyplot + grafovi (headless -> PNG)
REM  Generira skyplot.png i otvara ga.
REM
REM  Primjeri:
REM    run_skyplot.bat
REM    run_skyplot.bat --lat 51.5074 --lon -0.1278 --seconds 300
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0skyplot.py" --out "%~dp0skyplot.png" %*
if exist "%~dp0skyplot.png" start "" "%~dp0skyplot.png"

echo.
pause
endlocal
