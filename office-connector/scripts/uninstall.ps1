param(
  [Parameter(Mandatory=$false)][string]$DllPath,
  [ValidateSet("x86","x64")][string]$OfficeBitness = "x64",
  [Parameter(Mandatory=$false)][string]$TargetSid
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($TargetSid)) {
  $TargetSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -DllPath `"$DllPath`" -OfficeBitness $OfficeBitness -TargetSid $TargetSid"
  $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments -Wait -PassThru
  exit $process.ExitCode
}
$entries = @(
  @{ App="Word"; ProgId="DocFlow.WordAddin" },
  @{ App="Excel"; ProgId="DocFlow.ExcelAddin" },
  @{ App="Visio"; ProgId="DocFlow.VisioAddin" }
)
foreach ($entry in $entries) {
  $key = "Registry::HKEY_USERS\$TargetSid\Software\Microsoft\Office\$($entry.App)\Addins\$($entry.ProgId)"
  Remove-Item -Path $key -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not [string]::IsNullOrWhiteSpace($DllPath) -and (Test-Path $DllPath)) {
  $framework = if ($OfficeBitness -eq "x86") {
    Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\RegAsm.exe"
  } else {
    Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"
  }
  if (Test-Path $framework) {
    & $framework (Resolve-Path $DllPath).Path /unregister
    if ($LASTEXITCODE -ne 0) { throw "RegAsm /unregister завершился с кодом $LASTEXITCODE" }
  }
}
Write-Host "Надстройки DocFlow удалены из Word, Excel и Visio." -ForegroundColor Green
