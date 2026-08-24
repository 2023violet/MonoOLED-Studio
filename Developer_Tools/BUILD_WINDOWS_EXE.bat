@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."

echo ============================================================
echo  MonoOLED Studio v8.4.3 - Windows Release ^& Real-Qt GA Builder
echo ============================================================

set "PY_CMD=py -3.13"
%PY_CMD% -c "import sys; assert sys.version_info >= (3,13)" >nul 2>&1
if errorlevel 1 (
  set "PY_CMD=py -3"
  %PY_CMD% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
  if errorlevel 1 (
    set "PY_CMD=python"
    %PY_CMD% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
    if errorlevel 1 (
      echo [FAIL] Python 3.10+ not found. Python 3.13 x64 is recommended.
      exit /b 2
    )
  )
)

if not exist ".venv-build\Scripts\python.exe" (
  echo [1/18] Creating isolated build environment...
  %PY_CMD% -m venv .venv-build || exit /b 2
)
set "VPY=.venv-build\Scripts\python.exe"

echo [2/18] Installing pinned build and test dependencies...
"%VPY%" -m pip install --upgrade pip || exit /b 2
"%VPY%" -m pip install -r "OLED模拟器\requirements-build.txt" || exit /b 2
"%VPY%" -m pip install -r "OLED模拟器\requirements-dev.txt" || exit /b 2

echo [3/18] Verifying Windows release text / CRLF contract...
"%VPY%" Developer_Tools\VERIFY_WINDOWS_RELEASE_TEXT.py || exit /b 2

echo [4/18] Running bounded non-Qt source regression groups...
"%VPY%" Developer_Tools\RUN_WINDOWS_TEST_GROUPS.py --phase source --python "%VPY%" --report-dir "OLED模拟器\reports\windows_ga" --source-group-size 8 --group-timeout 300 || exit /b 2

echo [5/18] Running core + real-window startup checks...
"%VPY%" "OLED模拟器\gui.py" --check || exit /b 2
"%VPY%" "OLED模拟器\gui.py" --startup-smoke || exit /b 2

echo [6/18] Running isolated Real-Qt modules at 8 DPI scales with ZERO-SKIP enforcement...
rem Mandatory scales: 1.0 1.25 1.5 1.75 2.0 2.25 2.5 3.0
rem Historical mandatory Real-Qt suites remain auto-discovered from test_qt_*.py:
rem test_qt_real_interactions_v51.py test_qt_v80_unified_workspace.py
rem test_qt_v82_studio_select_state_machine.py test_qt_v82_preferences_theme_surface.py
rem test_qt_v83_reliability.py test_qt_v84_project_automation.py
rem RUN_WINDOWS_TEST_GROUPS.py invokes VERIFY_JUNIT_NO_SKIPS.py for each isolated Qt module.
rem It also runs --startup-smoke and --layout-smoke per QT_SCALE_FACTOR.
"%VPY%" Developer_Tools\RUN_WINDOWS_TEST_GROUPS.py --phase qt --python "%VPY%" --report-dir "OLED模拟器\reports\windows_ga" --qt-timeout 300 --scales "1.0,1.25,1.5,1.75,2.0,2.25,2.5,3.0" || exit /b 2

echo [7/18] Running V8.2 native visual adversarial gate...
"%VPY%" Developer_Tools\VERIFY_V82_STRESS.py || exit /b 2

echo [8/18] Running V8.3 reliability/performance gate...
"%VPY%" Developer_Tools\VERIFY_V83_STRESS.py || exit /b 2

echo [9/18] Running V8.4 final Project/Code-AI graduation gate...
"%VPY%" Developer_Tools\VERIFY_V84_FINAL.py || exit /b 2

echo [10/18] Running V8.4.1 Automation State Model graduation gate...
"%VPY%" Developer_Tools\VERIFY_V841_FINAL.py || exit /b 2

echo [11/18] Running V8.4.2 Automation Reliability/data-safety gate...
"%VPY%" Developer_Tools\VERIFY_V842_FINAL.py || exit /b 2

echo [12/18] Running V8.4.3 Windows release closure gate...
"%VPY%" Developer_Tools\VERIFY_V843_FINAL.py || exit /b 2

echo [13/18] Building PyInstaller onedir application...
if exist build rmdir /s /q build
if exist "dist\MonoOLEDStudio" rmdir /s /q "dist\MonoOLEDStudio"
"%VPY%" -m PyInstaller --clean --noconfirm Developer_Tools\MonoOLEDStudio.spec || exit /b 2

set "APP=dist\MonoOLEDStudio\MonoOLEDStudio.exe"
if not exist "%APP%" (
  echo [FAIL] Expected executable not created: %APP%
  exit /b 2
)

echo [14/18] Executable core check...
"%APP%" --check || exit /b 2

echo [15/18] Executable real-window startup + layout smoke...
"%APP%" --startup-smoke || exit /b 2
"%APP%" --smoke-ms 900 || exit /b 2
"%APP%" --layout-smoke || exit /b 2

echo [16/18] Executable interaction smoke...
"%APP%" --interaction-smoke || exit /b 2

echo [17/18] Executable soak smoke...
"%APP%" --soak-smoke || exit /b 2

echo [18/18] Creating release ZIP and SHA-256...
if not exist release mkdir release
for /f "usebackq delims=" %%V in ("OLED模拟器\VERSION") do set "VER=%%V"
set "ZIP=release\MonoOLEDStudio_v%VER%_Windows_x64.zip"
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\MonoOLEDStudio\*' -DestinationPath '%ZIP%' -CompressionLevel Optimal" || exit /b 2
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash -Algorithm SHA256 '%ZIP%').Hash.ToLower(); Set-Content -Encoding ascii '%ZIP%.sha256' ($h + '  ' + [IO.Path]::GetFileName('%ZIP%')); Write-Host ('SHA256 ' + $h)" || exit /b 2

echo.
echo [PASS] Windows GA candidate created after bounded zero-skip Real-Qt gate:
echo        %ZIP%
echo        %ZIP%.sha256
exit /b 0
