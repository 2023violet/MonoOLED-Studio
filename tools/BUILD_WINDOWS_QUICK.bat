@echo off

setlocal EnableExtensions

chcp 65001 >nul

cd /d "%~dp0.."

for /f "usebackq delims=" %%V in ("src\VERSION") do set "VER=%%V"
if not defined VER ( echo [FAIL] src\VERSION is empty & exit /b 2 )



echo ============================================================

echo  MonoOLED Studio V%VER% - Quick Windows EXE Builder

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

  echo [1/5] Creating reusable build environment...

  %PY_CMD% -m venv .venv-build || exit /b 2

)

set "VPY=.venv-build\Scripts\python.exe"



"%VPY%" -c "import PySide6; import PyInstaller" >nul 2>&1

if errorlevel 1 (

  echo [2/5] Installing build dependencies ^(first run only^)...

  "%VPY%" -m pip install --upgrade pip || exit /b 2

  "%VPY%" -m pip install -r requirements-build.txt || exit /b 2

) else (

  echo [2/5] Reusing installed build dependencies.

)



echo [3/5] Building current source with PyInstaller...

if exist build rmdir /s /q build

if exist "dist\MonoOLEDStudio" rmdir /s /q "dist\MonoOLEDStudio"

"%VPY%" -m PyInstaller --clean --noconfirm tools\MonoOLEDStudio.spec || exit /b 2



set "APP=dist\MonoOLEDStudio\MonoOLEDStudio.exe"

if not exist "%APP%" (

  echo [FAIL] Expected executable not created: %APP%

  exit /b 2

)



echo [4/5] Running executable core check...

"%APP%" --check || exit /b 2



echo [5/5] Running one startup smoke...

"%APP%" --startup-smoke || exit /b 2



echo.

echo [PASS] Quick EXE created:

echo        %APP%

echo [INFO] For a signed-off release candidate use tools\BUILD_WINDOWS_GA.bat.

exit /b 0

