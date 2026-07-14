@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  snimanje/reprodukcija scenarija (headless)
REM  Primjeri:
REM    run_scenario.bat list
REM    run_scenario.bat run scenarios\spoof_coordinated.json
REM    run_scenario.bat compare scenarios\jamming_naive_spoof.json
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0scenario.py" %*

echo.
pause
endlocal
