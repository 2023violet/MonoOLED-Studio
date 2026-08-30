@echo off

setlocal EnableExtensions EnableDelayedExpansion

chcp 65001 >nul

cd /d "%~dp0.."

for /f "usebackq delims=" %%V in ("src\VERSION") do set "VER=%%V"
if not defined VER ( echo [FAIL] src\VERSION is empty & exit /b 2 )



echo ============================================================

echo  MonoOLED Studio V%VER% - Windows Release Integrity GA Builder

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

  echo [1/22] Creating isolated build environment...

  %PY_CMD% -m venv .venv-build || exit /b 2

)

set "VPY=.venv-build\Scripts\python.exe"

if exist ".artifacts\windows_ga" rmdir /s /q ".artifacts\windows_ga"
mkdir ".artifacts\windows_ga"

echo [2/22] Installing pinned build and test dependencies...

"%VPY%" -m pip install --upgrade pip || exit /b 2

"%VPY%" -m pip install -r "requirements-build.txt" || exit /b 2

"%VPY%" -m pip install -r "requirements-dev.txt" || exit /b 2



echo [3/22] Verifying Windows release text / CRLF contract...

"%VPY%" tools\VERIFY_WINDOWS_RELEASE_TEXT.py || exit /b 2



rem Current source test root: tests\

echo [4/22] Running bounded non-Qt source regression groups...

"%VPY%" tools\RUN_WINDOWS_TEST_GROUPS.py --phase source --python "%VPY%" --report-dir ".artifacts\windows_ga" --source-group-size 8 --group-timeout 300 || exit /b 2



echo [5/22] Running core check...

"%VPY%" "src\gui.py" --check || exit /b 2



echo [6/22] Running source startup smoke 20 consecutive times...

for /L %%I in (1,1,20) do (

  echo [SOURCE STARTUP %%I/20]

  "%VPY%" "src\gui.py" --startup-smoke || exit /b 2

)



echo [6A/22] Running source Font Lab critical-path smoke...

"%VPY%" "src\gui.py" --font-smoke || exit /b 2


echo [7/22] Running isolated Real-Qt modules at 8 DPI scales with ZERO-SKIP enforcement...

rem Mandatory scales: 1.0 1.25 1.5 1.75 2.0 2.25 2.5 3.0

rem Historical mandatory Real-Qt suites remain auto-discovered from test_qt_*.py:

rem test_qt_real_interactions_v51.py test_qt_v80_unified_workspace.py

rem test_qt_v82_studio_select_state_machine.py test_qt_v82_preferences_theme_surface.py

rem test_qt_v83_reliability.py test_qt_v84_project_automation.py

rem RUN_WINDOWS_TEST_GROUPS.py invokes VERIFY_JUNIT_NO_SKIPS.py for each isolated Qt module.

rem Historical release gates remain regression-covered by the current source/Qt inventory;

rem they are NOT executed as standalone version-locked scripts in current V12 GA:

rem VERIFY_V82_STRESS.py VERIFY_V83_STRESS.py VERIFY_V84_FINAL.py VERIFY_V841_FINAL.py

rem VERIFY_V842_FINAL.py VERIFY_V843_FINAL.py VERIFY_V844_FINAL.py

rem VERIFY_ACCENT_RAIL_V102.py VERIFY_MICRO_SIGNATURE_V103.py VERIFY_V104_UX_STABILITY.py

rem VERIFY_V11_GENERIC_WORKBENCH.py VERIFY_V111_USABILITY_STABILITY.py VERIFY_V112_PIXEL_GITHUB_RELEASE.py

rem It also runs --startup-smoke and --layout-smoke per QT_SCALE_FACTOR.

"%VPY%" tools\RUN_WINDOWS_TEST_GROUPS.py --phase qt --python "%VPY%" --report-dir ".artifacts\windows_ga" --qt-timeout 600 --scales "1.0,1.25,1.5,1.75,2.0,2.25,2.5,3.0" || exit /b 2



echo [7A/22] Running V12.3.1 Settings reliability smoke + 500-cycle soak...

"%VPY%" tools\VERIFY_SETTINGS_V1231.py || exit /b 2



echo [7B/22] Capturing V12.3.1 Settings visual evidence matrix...

"%VPY%" tools\CAPTURE_V1231_SETTINGS_GOLDENS.py --output ".artifacts\windows_ga\settings_v1231_golden" || exit /b 2



echo [8/14] Running current V12 package contract...

"%VPY%" VERIFY_PACKAGE.py || exit /b 2



echo [9/14] Running current V12 native Generic Product Closure gate...

"%VPY%" tools\VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py || exit /b 2



echo [10/14] Building PyInstaller onedir application...

if exist build rmdir /s /q build

if exist "dist\MonoOLEDStudio" rmdir /s /q "dist\MonoOLEDStudio"

"%VPY%" -m PyInstaller --clean --noconfirm tools\MonoOLEDStudio.spec || exit /b 2



set "APP=dist\MonoOLEDStudio\MonoOLEDStudio.exe"

if not exist "%APP%" (

  echo [FAIL] Expected executable not created: %APP%

  exit /b 2

)



echo [11/14] Executable core check...

"%APP%" --check || exit /b 2



echo [12/14] Executable startup smoke 20 consecutive times...

for /L %%I in (1,1,20) do (

  echo [EXE STARTUP %%I/20]

  "%APP%" --startup-smoke || exit /b 2

)



echo [12A/14] Executable Font Lab critical-path smoke...

"%APP%" --font-smoke || exit /b 2


echo [13/14] Executable visible-window smoke...

"%APP%" --smoke-ms 900 || exit /b 2



echo [13A/14] Executable layout smoke 5 consecutive times...

for /L %%I in (1,1,5) do (

  echo [EXE LAYOUT %%I/5]

  "%APP%" --layout-smoke || exit /b 2

)



echo [13A2/14] Executable Settings boundary smoke 5 consecutive times...

for /L %%I in (1,1,5) do (

  echo [EXE SETTINGS %%I/5]

  "%APP%" --settings-smoke || exit /b 2

)



echo [13A3/14] Executable Settings 500-cycle soak...

"%APP%" --settings-soak --settings-soak-cycles 500 || exit /b 2



echo [13B/14] Executable interaction smoke 5 consecutive times...

for /L %%I in (1,1,5) do (

  echo [EXE INTERACTION %%I/5]

  "%APP%" --interaction-smoke || exit /b 2

)



echo [13C/14] Executable soak smoke 10 x 240 cycles...

for /L %%I in (1,1,10) do (

  echo [EXE SOAK %%I/10]

  "%APP%" --soak-smoke || exit /b 2

)



echo [14/14] Creating deterministic release ZIP, provenance and SHA-256...

if not exist release mkdir release

for /f "usebackq delims=" %%V in ("src\VERSION") do set "VER=%%V"

set "ZIP=release\MonoOLEDStudio_v%VER%_Windows_x64.zip"
set "GIT_COMMIT=unavailable"
for /f "delims=" %%C in ('git rev-parse HEAD 2^>nul') do set "GIT_COMMIT=%%C"

"%VPY%" tools\BUILD_WINDOWS_RUNTIME_ZIP.py --app-dir "dist\MonoOLEDStudio" --output "%ZIP%" --version "%VER%" --git-commit "%GIT_COMMIT%" || exit /b 2

"%VPY%" tools\BUILD_WINDOWS_RUNTIME_ZIP.py --verify "%ZIP%" --expected-version "%VER%" --checksum "%ZIP%.sha256" --expected-git-commit "%GIT_COMMIT%" --extract-to ".artifacts\windows_ga\release_extract" || exit /b 2

set "PACKAGED_APP=.artifacts\windows_ga\release_extract\MonoOLEDStudio.exe"
if not exist "%PACKAGED_APP%" (
  echo [FAIL] Packaged executable not found after extraction: %PACKAGED_APP%
  exit /b 2
)

echo [PACKAGED CHECK] Running end-user ZIP executable checks...
"%PACKAGED_APP%" --check || exit /b 2
"%PACKAGED_APP%" --startup-smoke || exit /b 2
"%PACKAGED_APP%" --layout-smoke || exit /b 2
"%PACKAGED_APP%" --settings-smoke || exit /b 2
"%PACKAGED_APP%" --font-smoke || exit /b 2
"%PACKAGED_APP%" --interaction-smoke || exit /b 2



echo.

echo [PASS] Windows GA candidate created after bounded zero-skip Real-Qt gate:

echo        %ZIP%

echo        %ZIP%.sha256

exit /b 0

