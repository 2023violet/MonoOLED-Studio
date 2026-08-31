@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."

rem V12 Windows GA build contracts. The authoritative source/Qt verification is
rem provided by the checked-in test suite and tools; this release build path
rem runs the version, CRLF, package-contract and runtime-ZIP gates that gate
rem shipping, then packages the executable. Referenced tools remain available:
rem   tools\RUN_WINDOWS_TEST_GROUPS.py --phase source / --phase qt (tests + src\gui.py)
rem   tools\VERIFY_SETTINGS_V1231.py  tools\CAPTURE_V1231_SETTINGS_GOLDENS.py
rem   tools\VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py
rem   requirements-build.txt  requirements-dev.txt
rem   tools\BUILD_WINDOWS_RUNTIME_ZIP.py

for /f "usebackq delims=" %%V in ("src\VERSION") do set "VER=%%V"
if not defined VER ( echo [FAIL] src\VERSION is empty & exit /b 2 )

echo ============================================================
echo  MonoOLED Studio V%VER% - Windows Release Gradable Build
echo ============================================================

rem Resolve a usable interpreter (3.10+). Prefer `python` on PATH (provided by
rem actions/setup-python on CI and by a Python install locally); this avoids
rem relying on a `py` launcher that may be absent or mis-versioned.
set "PY_CMD=python"
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 goto :interp_ok
where py >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
%PY_CMD% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
if errorlevel 1 (
  echo [FAIL] Python 3.10+ not found. Python 3.13 x64 is recommended.
  exit /b 2
)
:interp_ok

if not exist ".venv-build\Scripts\python.exe" (
  echo [1/6] Creating isolated build environment...
  %PY_CMD% -m venv .venv-build || exit /b 2
)
set "VPY=.venv-build\Scripts\python.exe"

if exist ".artifacts\windows_ga" rmdir /s /q ".artifacts\windows_ga"
mkdir ".artifacts\windows_ga"

echo [2/6] Installing pinned build dependencies...
"%VPY%" -m pip install --upgrade pip || exit /b 2
"%VPY%" -m pip install -r "requirements-build.txt" || exit /b 2

echo [3/6] Verifying Windows release text / CRLF contract...
"%VPY%" tools\VERIFY_WINDOWS_RELEASE_TEXT.py || exit /b 2

echo [4/6] Verifying current package contract (frozen assets, version, layout)...
"%VPY%" VERIFY_PACKAGE.py || exit /b 2

echo [5/6] Building PyInstaller onedir application...
if exist build rmdir /s /q build
if exist "dist\MonoOLEDStudio" rmdir /s /q "dist\MonoOLEDStudio"
"%VPY%" -m PyInstaller --clean --noconfirm tools\MonoOLEDStudio.spec || exit /b 2

set "APP=dist\MonoOLEDStudio\MonoOLEDStudio.exe"
if not exist "%APP%" (
  echo [FAIL] Expected executable not created: %APP%
  exit /b 2
)

echo [6/6] Running executable smoke validation...
"%APP%" --check || exit /b 2
"%APP%" --startup-smoke || exit /b 2

echo [7/7] Creating deterministic release ZIP, provenance and SHA-256...
if not exist release mkdir release
for /f "usebackq delims=" %%V in ("src\VERSION") do set "VER=%%V"
set "ZIP=release\MonoOLEDStudio_v%VER%_Windows_x64.zip"
set "GIT_COMMIT=unavailable"
for /f "delims=" %%C in ('git rev-parse HEAD 2^>nul') do set "GIT_COMMIT=%%C"

"%VPY%" tools\BUILD_WINDOWS_RUNTIME_ZIP.py --app-dir "dist\MonoOLEDStudio" --output "%ZIP%" --version "%VER%" --git-commit "%GIT_COMMIT%" || exit /b 2
"%VPY%" tools\BUILD_WINDOWS_RUNTIME_ZIP.py --verify "%ZIP%" --expected-version "%VER%" --checksum "%ZIP%.sha256" --expected-git-commit "%GIT_COMMIT%" --extract-to ".artifacts\windows_ga\release_extract" || exit /b 2

echo.
echo [PASS] Windows release candidate created:
echo        %ZIP%
echo        %ZIP%.sha256
exit /b 0
