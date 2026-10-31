@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Запуск: start.bat [IP] [ПОРТ]   (по умолчанию 0.0.0.0 8000)
set HOST=%~1
set PORT=%~2
if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8000
set PYCMD=
py -3.12 -V >nul 2>nul && set PYCMD=py -3.12
if not defined PYCMD python -V >nul 2>nul && set PYCMD=python
if not defined PYCMD (
  echo Python 3.12 не найден. Установите: https://www.python.org/downloads/ ^(отметьте Add python.exe to PATH^)
  pause
  exit /b 1
)
%PYCMD% run.py %HOST% %PORT%
pause
