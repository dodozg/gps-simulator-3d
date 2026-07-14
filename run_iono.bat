@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  Klobuchar ionosferska analiza (headless)
REM  Dnevna krivulja TEC-a + ovisnost o elevaciji -> iono.png
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0iono.py" %*

echo.
pause
endlocal
