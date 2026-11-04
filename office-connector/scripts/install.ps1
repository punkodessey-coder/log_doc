param(
  [Parameter(Mandatory=$true)][string]$DllPath
)
$ErrorActionPreference = "Stop"
$full = (Resolve-Path $DllPath).Path
$framework = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"
if (-not (Test-Path $framework)) { $framework = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\RegAsm.exe" }
if (-not (Test-Path $framework)) { throw ".NET Framework RegAsm.exe не найден." }
& $framework $full /codebase
if ($LASTEXITCODE -ne 0) { throw "RegAsm завершился с кодом $LASTEXITCODE" }
$entries = @(
  @{ App="Word"; ProgId="DocFlow.WordAddin"; Description="DocFlow Office Connector for Word" },
  @{ App="Excel"; ProgId="DocFlow.ExcelAddin"; Description="DocFlow Office Connector for Excel" },
  @{ App="Visio"; ProgId="DocFlow.VisioAddin"; Description="DocFlow Office Connector for Visio" }
)
foreach ($entry in $entries) {
  $key = "HKCU:\Software\Microsoft\Office\$($entry.App)\Addins\$($entry.ProgId)"
  New-Item -Path $key -Force | Out-Null
  New-ItemProperty -Path $key -Name FriendlyName -Value $entry.Description -PropertyType String -Force | Out-Null
  New-ItemProperty -Path $key -Name Description -Value $entry.Description -PropertyType String -Force | Out-Null
  New-ItemProperty -Path $key -Name LoadBehavior -Value 3 -PropertyType DWord -Force | Out-Null
}
Write-Host "DocFlow Office Connector зарегистрирован для Word, Excel и Visio." -ForegroundColor Green
