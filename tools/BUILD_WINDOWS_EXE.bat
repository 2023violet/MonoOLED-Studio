@echo off

setlocal EnableExtensions

chcp 65001 >nul

cd /d "%~dp0.."

for /f "usebackq delims=" %%V in ("src\VERSION") do set "VER=%%V"
if not defined VER ( echo [FAIL] src\VERSION is empty & exit /b 2 )

echo ============================================================

echo  MonoOLED Studio V%VER% - Compatibility Builder

echo ============================================================

echo [INFO] BUILD_WINDOWS_EXE.bat is retained only for compatibility.

echo [INFO] Fast local EXE: tools\BUILD_WINDOWS_QUICK.bat

echo [INFO] Full release GA: tools\BUILD_WINDOWS_GA.bat

echo.

call tools\BUILD_WINDOWS_GA.bat

exit /b %ERRORLEVEL%

