@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "BUILT=dist\MonoOLEDStudio\MonoOLEDStudio.exe"
if exist "%BUILT%" (
  start "" "%BUILT%"
  exit /b 0
)

rem Prefer the managed runtime created by INSTALL_RUNTIME.bat. This avoids
rem relying on PATH, shebang parsing, or a portable-python folder layout.
set "VPY=.venv-runtime\Scripts\python.exe"
set "VPYW=.venv-runtime\Scripts\pythonw.exe"
if exist "%VPY%" (
  "%VPY%" -c "import PySide6, PIL" >nul 2>nul
  if errorlevel 1 (
    echo [FAIL] Managed runtime exists but dependencies are incomplete.
    echo        Re-run INSTALL_RUNTIME.bat.
    pause
    exit /b 2
  )
  if exist "%VPYW%" (
    start "" "%VPYW%" "src\gui.py"
  ) else (
    "%VPY%" "src\gui.py"
    if errorlevel 1 pause
  )
  exit /b %errorlevel%
)

echo [INFO] No standalone build or managed runtime was found.
echo        Recommended: run INSTALL_RUNTIME.bat once for source mode,
echo        or BUILD_WINDOWS_EXE.bat for a standalone Windows release.
echo.
echo        Direct source launch remains supported:
echo        python "src\gui.py"
pause
exit /b 2
