@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."

if not exist ".venv-runtime\Scripts\python.exe" (
  echo [INFO] Controlled runtime is missing; creating it first...
  call Developer_Tools\CREATE_RUNTIME_ENV.bat || exit /b 2
)

set "PY=.venv-runtime\Scripts\python.exe"
echo [1/2] Real GUI startup smoke...
"%PY%" "OLED模拟器\gui.py" --project "CuringLite.project.oled.json" --startup-smoke || exit /b 2

echo [2/2] Starting MonoOLED Studio with diagnostic console and runtime log...
"%PY%" "OLED模拟器\gui.py" --project "CuringLite.project.oled.json"
set "RC=%ERRORLEVEL%"
echo.
echo MonoOLED Studio exited with code %RC%.
echo Runtime diagnostics are under the project log directory as monoled_runtime.log.
pause
exit /b %RC%
