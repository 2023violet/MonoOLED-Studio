@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "BUILT=dist\MonoOLEDStudio\MonoOLEDStudio.exe"
if exist "%BUILT%" (
  "%BUILT%" --check || goto :fail
  echo OLED standalone EXE check PASS.
  exit /b 0
)

set "VPY=.venv-runtime\Scripts\python.exe"
if exist "%VPY%" (
  "%VPY%" "src\gui.py" --check || goto :fail
  "%VPY%" "src\cli.py" validate || goto :fail
  echo OLED managed-runtime check PASS.
  exit /b 0
)

echo [INFO] No built EXE or managed runtime found.
echo        Run INSTALL_RUNTIME.bat or BUILD_WINDOWS_EXE.bat first.
exit /b 2

:fail
echo OLED tool check FAILED.
pause
exit /b 1
