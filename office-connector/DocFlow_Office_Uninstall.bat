@echo off
setlocal
chcp 65001 >nul
title DocFlow Office Connector — удаление
echo.
echo ==========================================
echo   Удаление DocFlow Office Connector
echo ==========================================
echo.
echo Закройте Word, Excel и Visio перед продолжением.
echo Удаление не затрагивает документы на сервере DocFlow.
echo.
set "DF_SCRIPT=%~dp0scripts\uninstall.ps1"
if not exist "%DF_SCRIPT%" (
  echo Не найден локальный файл:
  echo "%DF_SCRIPT%"
  echo Убедитесь, что папка scripts находится рядом с этим BAT.
  pause
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DF_SCRIPT%"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Удаление завершилось с ошибкой. Код: %RC%
) else (
  echo DocFlow Office Connector удалён.
)
pause
exit /b %RC%
