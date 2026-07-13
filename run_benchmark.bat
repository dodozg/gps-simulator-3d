@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  headless benchmark (bez GPU-a)
REM
REM  Vrti simulaciju bez 3D prikaza i ispisuje statistiku greske,
REM  NIS/dof i RAIM alarme. Trebaju samo numpy paketi pa radi i
REM  kad 3D prikaz (VTK) nije dostupan.
REM
REM  Primjeri:
REM    run_benchmark.bat
REM    run_benchmark.bat --lat 51.5074 --lon -0.1278 --seconds 300
REM ============================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0.venv\Lib\site-packages"

python "%~dp0benchmark.py" %*

echo.
pause
endlocal
