@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  carrier-phase RTK demo (headless)
REM  Pokazuje cm-precizno relativno pozicioniranje vs kodno (~m).
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0rtk.py" %*

echo.
pause
endlocal
