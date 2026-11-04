@echo off
setlocal
title DocFlow Office Connector - Installer
echo.
echo ==========================================
echo   DocFlow Office Connector
echo ==========================================
echo.
echo This installer downloads the latest x64 Office connector build
echo from the GitHub Actions artifacts of punkodessey-coder/log_doc.
echo.

set "WORK=%TEMP%\DocFlowOfficeConnector"
if not exist "%WORK%" mkdir "%WORK%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $repo='punkodessey-coder/log_doc'; $name='DocFlow-Office-Connector-Win11-Office-x64'; $api='https://api.github.com/repos/'+$repo+'/actions/artifacts?per_page=100'; $headers=@{ 'User-Agent'='DocFlow-Office-Connector-Installer'; 'Accept'='application/vnd.github+json' }; $data=Invoke-RestMethod -Uri $api -Headers $headers; $a=$data.artifacts | Where-Object { $_.name -eq $name -and -not $_.expired } | Sort-Object created_at -Descending | Select-Object -First 1; if(-not $a){ throw 'No active build artifact found. Check repository access and GitHub Actions.' }; $zip=Join-Path $env:TEMP 'DocFlow-Office-Connector.zip'; Invoke-WebRequest -Uri $a.archive_download_url -Headers $headers -OutFile $zip; $dest=Join-Path $env:TEMP 'DocFlow-Office-Connector-Package'; if(Test-Path $dest){Remove-Item $dest -Recurse -Force}; Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force; $installer=Get-ChildItem -Path $dest -Filter 'УСТАНОВИТЬ.bat' -Recurse | Select-Object -First 1; if(-not $installer){ throw 'УСТАНОВИТЬ.bat was not found inside the downloaded package.' }; Start-Process -FilePath $installer.FullName -Wait; if($LASTEXITCODE -ne 0){ exit $LASTEXITCODE }"
if errorlevel 1 (
  echo.
  echo Installation failed. The repository may be private or the build artifact may be unavailable.
  pause
  exit /b 1
)
echo.
echo Installation process finished. Restart Word, Excel and Visio.
pause
