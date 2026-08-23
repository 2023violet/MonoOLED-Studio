@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PY=py -3.13"
%PY% -c "import sys" >nul 2>nul
if errorlevel 1 (
  set "PY=py -3"
  %PY% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
  if errorlevel 1 set "PY=python"
)
%PY% -m pytest "OLED模拟器\tests" -q
if errorlevel 1 pause
exit /b %errorlevel%
