param(
  [Parameter(Mandatory=$true)][string]$DllPath,
  [ValidateSet("x86","x64")][string]$OfficeBitness = "x64",
  [Parameter(Mandatory=$false)][string]$TargetSid
)
$ErrorActionPreference = "Stop"

# Preserve the interactive user's Office add-in registration even when RegAsm
# is elevated. The installer passes the original user's SID before UAC elevation.
if ([string]::IsNullOrWhiteSpace($TargetSid)) {
  $TargetSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}
if (-not (Test-Path "Registry::HKEY_USERS\$TargetSid")) {
  throw "Профиль пользователя $TargetSid не загружен. Запустите установку из своей учётной записи Windows."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -DllPath `"$DllPath`" -OfficeBitness $OfficeBitness -TargetSid $TargetSid"
  $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments -Wait -PassThru
  exit $process.ExitCode
}
$full = (Resolve-Path $DllPath).Path
$framework = if ($OfficeBitness -eq "x86") {
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
  $key = "Registry::HKEY_USERS\$TargetSid\Software\Microsoft\Office\$($entry.App)\Addins\$($entry.ProgId)"
  New-Item -Path $key -Force | Out-Null
  New-ItemProperty -Path $key -Name FriendlyName -Value $entry.Description -PropertyType String -Force | Out-Null
  New-ItemProperty -Path $key -Name Description -Value $entry.Description -PropertyType String -Force | Out-Null
  New-ItemProperty -Path $key -Name LoadBehavior -Value 3 -PropertyType DWord -Force | Out-Null
}
Write-Host "DocFlow Office Connector зарегистрирован для Word, Excel и Visio (Office $OfficeBitness)." -ForegroundColor Green
