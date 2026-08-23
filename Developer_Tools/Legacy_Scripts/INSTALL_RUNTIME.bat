@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PY=py -3.13"
%PY% -c "import sys" >nul 2>nul
if errorlevel 1 (
  set "PY=py -3"
  %PY% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
  if errorlevel 1 (
    set "PY=python"
    %PY% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
    if errorlevel 1 (
      echo [FAIL] Python 3.10+ not found. Python 3.13 x64 is recommended.
      pause
      exit /b 2
    )
  )
)

if not exist ".venv-runtime\Scripts\python.exe" (
  %PY% -m venv .venv-runtime || exit /b 2
)
set "VPY=.venv-runtime\Scripts\python.exe"
set "VPYW=.venv-runtime\Scripts\pythonw.exe"

"%VPY%" -m pip install --upgrade pip || exit /b 2
"%VPY%" -m pip install -r "OLED模拟器\requirements.txt" || exit /b 2

rem Windows source-mode acceptance gates. Do not launch the editor when its
rem real Qt layout or interaction contract is already broken on this machine.
"%VPY%" "OLED模拟器\gui.py" --check || exit /b 2
"%VPY%" "OLED模拟器\gui.py" --layout-smoke || exit /b 2
"%VPY%" "OLED模拟器\gui.py" --interaction-smoke || exit /b 2

if not exist "%VPYW%" (
  echo [FAIL] Managed runtime does not contain pythonw.exe: %VPYW%
  pause
  exit /b 2
)

echo [PASS] Runtime installed and Windows Qt layout/interaction gates passed.
start "" "%VPYW%" "OLED模拟器\gui.py"
exit /b 0
