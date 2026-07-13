@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  pytest test suite
REM  Pokrece sve testove iz tests/ (bez GPU-a).
REM ============================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0.venv\Lib\site-packages"

python -m pytest %*

echo.
pause
endlocal
