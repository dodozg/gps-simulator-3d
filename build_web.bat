@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  build web frontenda (CesiumJS + TS)
REM  Google Drive nije NTFS pa node_modules/build ne mogu biti na G:.
REM  Zato se izvor kopira u lokalni dir (%LOCALAPPDATA%\gpsweb) i tamo builda.
REM  Traži Node.js (node --version).
REM ============================================================
setlocal
cd /d "%~dp0"
set "SRC=%~dp0web\frontend"
set "BUILD=%LOCALAPPDATA%\gpsweb"

where node >nul 2>&1 || ( echo [!] Node.js nije pronaden. Instaliraj Node 18+ i pokreni ponovno. & pause & exit /b 1 )

echo [i] Build dir: %BUILD%
if not exist "%BUILD%" mkdir "%BUILD%"
robocopy "%SRC%" "%BUILD%" package.json vite.config.ts tsconfig.json index.html /NJH /NJS /NFL /NDL >nul
robocopy "%SRC%\src" "%BUILD%\src" /MIR /NJH /NJS /NFL /NDL >nul

pushd "%BUILD%"
if not exist node_modules (
    echo [i] npm install ^(prvi put, moze potrajati^)...
    call npm install
)
echo [i] npm run build...
call npm run build
popd

if exist "%BUILD%\dist\index.html" (
    echo [OK] Frontend buildan: %BUILD%\dist
    echo      Sada pokreni run_webapp.bat
) else (
    echo [!] Build nije uspio - provjeri poruke iznad.
)
pause
endlocal
