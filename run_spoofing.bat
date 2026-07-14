@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  spoofing / jamming laboratorij (headless)
REM  Napadi na GNSS (spoof/meacon/jam) kroz pravi EKF/RAIM.
REM  Primjeri:
REM    run_spoofing.bat --attack coordinated --offset-e 600 --plot
REM    run_spoofing.bat --attack jamming --js-db 40
REM    run_spoofing.bat --attack naive --n 2 --bias 5000
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0spoofing.py" %*

echo.
pause
endlocal
