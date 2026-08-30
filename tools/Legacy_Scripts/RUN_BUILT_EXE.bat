@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "APP=dist\MonoOLEDStudio\MonoOLEDStudio.exe"
if not exist "%APP%" (
  echo [INFO] Standalone EXE has not been built yet.
  echo        Run BUILD_WINDOWS_EXE.bat first.
  pause
  exit /b 2
)
start "" "%APP%"
exit /b 0
