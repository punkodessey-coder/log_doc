param(
  [Parameter(Mandatory=$true)][string]$DllPath
)
$ErrorActionPreference = "Stop"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Для регистрации COM-классов запустите PowerShell от имени администратора."
}
$full = (Resolve-Path $DllPath).Path
$officeBitness = "x64"
try {
  $cfg = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction Stop
  if ($cfg.Platform -match "x86") { $officeBitness = "x86" }
} catch {}
$framework = if ($officeBitness -eq "x86") {
  Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\RegAsm.exe"
} else {
  Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"
}
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
