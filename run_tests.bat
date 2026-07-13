@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  pytest test suite (bez GPU-a)
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" -m pytest %*

echo.
pause
endlocal
