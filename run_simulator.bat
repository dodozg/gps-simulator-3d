@echo off
REM ============================================================
REM  GPS_Simulator_3D  -  3D simulator (PyVista / VTK GUI)
REM
REM  .venv je stvoren na drugom stroju pa je njegov python.exe
REM  pokvaren; zato koristimo sistemski Python + PYTHONPATH koji
REM  pokazuje na pakete unutar .venv (numpy, pyvista, PyQt5, vtk).
REM ============================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0.venv\Lib\site-packages"

echo Pokrecem GPS Simulator 3D...
echo   - Klikni na Zemlju za postavljanje prijemnika
echo   - 'D' = D.M.S format, 'M' = kinematski nacin
echo   - Zatvori prozor za izlaz
echo.

python "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo [GRESKA] Simulator je zavrsio s greskom - vidi poruke iznad.
    echo Ako pise "Application Control policy has blocked" radi se o
    echo Smart App Control-u koji blokira VTK DLL; vidi napomenu u chatu.
)
echo.
pause
endlocal
