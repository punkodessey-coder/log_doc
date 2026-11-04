param(
  [Parameter(Mandatory=$false)][string]$DllPath,
  [ValidateSet("x86","x64")][string]$OfficeBitness = "x64",
  [Parameter(Mandatory=$false)][string]$TargetSid
)
$ErrorActionPreference = "Stop"

# Keep registration cleanup scoped to the interactive user, even after UAC elevation.
if ([string]::IsNullOrWhiteSpace($TargetSid)) {
  $TargetSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}
if (-not (Test-Path "Registry::HKEY_USERS\$TargetSid")) {
  throw "Профиль пользователя $TargetSid не загружен. Запустите удаление из своей учётной записи Windows."
}

$officeProcesses = Get-Process WINWORD,EXCEL,VISIO -ErrorAction SilentlyContinue
if ($officeProcesses) {
  $names = ($officeProcesses | Select-Object -ExpandProperty ProcessName -Unique) -join ", "
  throw "Сначала полностью закройте приложения Office ($names), затем повторите удаление."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -DllPath `"$DllPath`" -OfficeBitness $OfficeBitness -TargetSid $TargetSid"
  $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments -Wait -PassThru
  exit $process.ExitCode
}

$entries = @(
  @{ App="Word"; ProgId="DocFlow.WordAddin"; Clsid="{B7D1C64C-84AE-4A67-9DB1-3B5C43E30101}" },
  @{ App="Excel"; ProgId="DocFlow.ExcelAddin"; Clsid="{B7D1C64C-84AE-4A67-9DB1-3B5C43E30102}" },
  @{ App="Visio"; ProgId="DocFlow.VisioAddin"; Clsid="{B7D1C64C-84AE-4A67-9DB1-3B5C43E30103}" }
)

# Remove Office's per-user add-in entries first.
foreach ($entry in $entries) {
  $key = "Registry::HKEY_USERS\$TargetSid\Software\Microsoft\Office\$($entry.App)\Addins\$($entry.ProgId)"
  Remove-Item -LiteralPath $key -Recurse -Force -ErrorAction SilentlyContinue
}

# RegAsm registration is architecture-specific. Unregister in both registry views
# so stale 32-bit or 64-bit COM entries cannot leave the add-in visible.
if (-not [string]::IsNullOrWhiteSpace($DllPath) -and (Test-Path -LiteralPath $DllPath)) {
  $fullDll = (Resolve-Path -LiteralPath $DllPath).Path
  $regAsmPaths = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\RegAsm.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe")
  )
  foreach ($regAsm in $regAsmPaths) {
    if (Test-Path $regAsm) {
      & $regAsm $fullDll /unregister
      if ($LASTEXITCODE -ne 0) { Write-Warning "RegAsm /unregister returned $LASTEXITCODE ($regAsm)" }
    }
  }
}

# Also remove only the known DocFlow ProgID/CLSID keys. This fallback works
# even if the original DLL was deleted or the old installation is incomplete.
foreach ($entry in $entries) {
  $progId = $entry.ProgId
  $clsid = $entry.Clsid
  $roots = @(
    "Registry::HKEY_USERS\$TargetSid\Software\Classes",
    "Registry::HKEY_LOCAL_MACHINE\Software\Classes",
    "Registry::HKEY_LOCAL_MACHINE\Software\Classes\WOW6432Node"
  )
  foreach ($root in $roots) {
    Remove-Item -LiteralPath (Join-Path $root $progId) -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $root "CLSID\$clsid") -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Remove-Item -LiteralPath (Join-Path $env:ProgramFiles "DocFlow\\OfficeConnector") -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "DocFlow удалён из Word, Excel и Visio. Записи COM-классов очищены для обеих разрядностей." -ForegroundColor Green
Write-Host "Документы и данные на сервере DocFlow не затронуты." -ForegroundColor Gray
