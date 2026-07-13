@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  headless benchmark (bez GPU-a)
REM  Ispisuje statistiku greske, NIS/dof i RAIM alarme.
REM
REM  Primjeri:
REM    run_benchmark.bat
REM    run_benchmark.bat --lat 51.5074 --lon -0.1278 --seconds 300
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0benchmark.py" %*

echo.
pause
endlocal
