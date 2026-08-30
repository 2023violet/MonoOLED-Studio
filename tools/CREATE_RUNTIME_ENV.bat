@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."

echo ============================================================
echo  MonoOLED Studio v8.4 - Runtime Environment Bootstrap
echo ============================================================

set "BASEPY="
if exist "C:\Program Files\Python313\python.exe" set "BASEPY=C:\Program Files\Python313\python.exe"
if not defined BASEPY (
  py -3.13 -c "import sys;print(sys.executable)" > "%TEMP%\monooled_py.txt" 2>nul
  if not errorlevel 1 set /p BASEPY=<"%TEMP%\monooled_py.txt"
)
if not defined BASEPY (
  python -c "import sys; assert sys.version_info >= (3,10); print(sys.executable)" > "%TEMP%\monooled_py.txt" 2>nul
  if not errorlevel 1 set /p BASEPY=<"%TEMP%\monooled_py.txt"
)
if not defined BASEPY (
  echo [FAIL] No Python 3.10+ runtime found. Python 3.13 x64 is recommended.
  exit /b 2
)

echo [1/4] Base Python: %BASEPY%
"%BASEPY%" -c "import PySide6,PIL; print('PySide6',PySide6.__version__)" || (
  echo [FAIL] The selected base Python does not contain PySide6 + Pillow.
  exit /b 2
)

if exist ".venv-runtime\Scripts\python.exe" rmdir /s /q ".venv-runtime"
echo [2/4] Creating .venv-runtime using --system-site-packages...
"%BASEPY%" -m venv --system-site-packages ".venv-runtime" || exit /b 2

set "VPY=.venv-runtime\Scripts\python.exe"
echo [3/4] Verifying controlled runtime...
"%VPY%" -c "import PySide6,PIL; print('Runtime OK:',PySide6.__version__)" || exit /b 2

echo [4/4] Running real Qt startup smoke...
if exist "test_assets/projects/curing_lite/project.oled.json" (
  "%VPY%" "src\gui.py" --project "test_assets/projects/curing_lite/project.oled.json" --startup-smoke || exit /b 2
) else (
  "%VPY%" "src\gui.py" --startup-smoke || exit /b 2
)

echo.
echo [PASS] .venv-runtime is ready.
echo        MonoOLEDStudio.exe will prefer this controlled runtime on the next launch.
exit /b 0
