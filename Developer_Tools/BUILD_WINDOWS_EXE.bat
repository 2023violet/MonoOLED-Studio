@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."

echo ============================================================
echo  MonoOLED Studio v8.4 - Windows GA Builder
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
  echo [1/15] Creating isolated build environment...
  %PY_CMD% -m venv .venv-build || exit /b 2
)
set "VPY=.venv-build\Scripts\python.exe"

echo [2/15] Installing pinned build and test dependencies...
"%VPY%" -m pip install --upgrade pip || exit /b 2
"%VPY%" -m pip install -r "OLED模拟器\requirements-build.txt" || exit /b 2
"%VPY%" -m pip install -r "OLED模拟器\requirements-dev.txt" || exit /b 2

echo [3/15] Running full source regression suite...
"%VPY%" -m pytest "OLED模拟器\tests" -q || exit /b 2

echo [4/15] Running core + real-window startup checks...
"%VPY%" "OLED模拟器\gui.py" --check || exit /b 2
"%VPY%" "OLED模拟器\gui.py" --startup-smoke || exit /b 2

echo [5/15] Running Real-Qt matrix with ZERO-SKIP enforcement...
rem Real-Qt inventory is discovered by test_qt_*.py; these retained markers
rem document mandatory historical gates: test_qt_v80_unified_workspace.py
rem test_qt_v82_studio_select_state_machine.py test_qt_v82_preferences_theme_surface.py
rem V8.3 adds test_qt_v83_reliability.py; V8.4 adds test_qt_v84_project_automation.py.
if not exist "OLED模拟器\reports\windows_qt" mkdir "OLED模拟器\reports\windows_qt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $qt=@(Get-ChildItem 'OLED模拟器\tests\test_qt_*.py' | ForEach-Object {$_.FullName}); if($qt.Count -eq 0){throw 'No Real-Qt tests found'}; foreach($s in @('1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0')) { Write-Host ('QT_SCALE_FACTOR=' + $s); $env:QT_SCALE_FACTOR=$s; $tag=$s.Replace('.','_'); $xml=('OLED模拟器\reports\windows_qt\qt_' + $tag + '.xml'); & '.venv-build\Scripts\python.exe' -m pytest @qt -q --junitxml=$xml; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}; & '.venv-build\Scripts\python.exe' 'Developer_Tools\VERIFY_JUNIT_NO_SKIPS.py' $xml; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}; & '.venv-build\Scripts\python.exe' 'OLED模拟器\gui.py' --startup-smoke; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}; & '.venv-build\Scripts\python.exe' 'OLED模拟器\gui.py' --layout-smoke; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE} }" || exit /b 2

echo [6/15] Running V8.2 native visual adversarial gate...
"%VPY%" Developer_Tools\VERIFY_V82_STRESS.py || exit /b 2

echo [7/15] Running V8.3 reliability/performance gate...
"%VPY%" Developer_Tools\VERIFY_V83_STRESS.py || exit /b 2

echo [8/15] Running V8.4 final Project/Code-AI graduation gate...
"%VPY%" Developer_Tools\VERIFY_V84_FINAL.py || exit /b 2

echo [9/15] Building PyInstaller onedir application...
if exist build rmdir /s /q build
if exist "dist\MonoOLEDStudio" rmdir /s /q "dist\MonoOLEDStudio"
"%VPY%" -m PyInstaller --clean --noconfirm Developer_Tools\MonoOLEDStudio.spec || exit /b 2

set "APP=dist\MonoOLEDStudio\MonoOLEDStudio.exe"
if not exist "%APP%" (
  echo [FAIL] Expected executable not created: %APP%
  exit /b 2
)

echo [10/15] Executable core check...
"%APP%" --check || exit /b 2

echo [11/15] Executable real-window startup smoke...
"%APP%" --startup-smoke || exit /b 2

echo [12/15] Executable short real-window smoke + layout matrix...
"%APP%" --smoke-ms 900 || exit /b 2
"%APP%" --layout-smoke || exit /b 2

echo [13/15] Executable interaction smoke...
"%APP%" --interaction-smoke || exit /b 2

echo [14/15] Executable soak smoke...
"%APP%" --soak-smoke || exit /b 2

echo [15/15] Creating release ZIP and SHA-256...
if not exist release mkdir release
for /f "usebackq delims=" %%V in ("OLED模拟器\VERSION") do set "VER=%%V"
set "ZIP=release\MonoOLEDStudio_v%VER%_Windows_x64.zip"
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\MonoOLEDStudio\*' -DestinationPath '%ZIP%' -CompressionLevel Optimal" || exit /b 2
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash -Algorithm SHA256 '%ZIP%').Hash.ToLower(); Set-Content -Encoding ascii '%ZIP%.sha256' ($h + '  ' + [IO.Path]::GetFileName('%ZIP%')); Write-Host ('SHA256 ' + $h)" || exit /b 2

echo.
echo [PASS] Windows GA candidate created after zero-skip Real-Qt gate:
echo        %ZIP%
echo        %ZIP%.sha256
exit /b 0
