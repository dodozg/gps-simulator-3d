@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  web kontrolni centar + GPS uciliste
REM  Pokrece FastAPI backend (uvicorn) i otvara preglednik.
REM  Frontend se posluzuje iz lokalnog builda (build_web.bat prije prvog pokretanja).
REM ============================================================
setlocal
cd /d "%~dp0"
set "GPSWEB_DIST=%LOCALAPPDATA%\gpsweb\dist"
if "%GPSWEB_PORT%"=="" set "GPSWEB_PORT=8010"
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import fastapi" >nul 2>&1 || (
    set "PY=python"
    set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
)

if not exist "%GPSWEB_DIST%\index.html" (
    echo [!] Frontend nije buildan - pokreni build_web.bat prvo.
    echo     ^(Backend ce svejedno raditi na /api, ali bez sucelja.^)
)

echo [i] Otvaram http://127.0.0.1:%GPSWEB_PORT%
start "" http://127.0.0.1:%GPSWEB_PORT%
"%PY%" -m uvicorn web.backend.app:app --host 127.0.0.1 --port %GPSWEB_PORT%

endlocal
