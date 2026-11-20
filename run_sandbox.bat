@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  istrazivacki sandbox (sweep x Monte Carlo)
REM  Primjeri:
REM    run_sandbox.bat list
REM    run_sandbox.bat validate sandbox\examples\raim_roc.json
REM    run_sandbox.bat run sandbox\examples\spoof_offset.json --workers 4 --plot
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import numpy" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

"%PY%" "%~dp0sandbox.py" %*

echo.
pause
endlocal
