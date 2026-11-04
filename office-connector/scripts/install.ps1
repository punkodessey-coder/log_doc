param([Parameter(Mandatory=$true)][string]$DllPath,[ValidateSet("Auto","x86","x64")][string]$OfficeBitness="Auto",[string]$TargetSid)
$ErrorActionPreference="Stop"
function Get-OfficeBitness {
  $ctr=Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction SilentlyContinue
  if($ctr -and $ctr.Platform -match '^(x86|x64)$'){return $ctr.Platform}
  foreach($key in @("HKLM:\SOFTWARE\Microsoft\Office\16.0\Word\InstallRoot","HKLM:\SOFTWARE\WOW6432Node\Microsoft\Office\16.0\Word\InstallRoot","HKLM:\SOFTWARE\Microsoft\Office\15.0\Word\InstallRoot","HKLM:\SOFTWARE\WOW6432Node\Microsoft\Office\15.0\Word\InstallRoot")){
    if(Test-Path $key){if($key -match 'WOW6432Node'){return "x86"}else{return "x64"}}
  }
  throw "Не удалось определить разрядность Office. Укажите x86 или x64."
}
if([string]::IsNullOrWhiteSpace($TargetSid)){$TargetSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value}
if(-not(Test-Path "Registry::HKEY_USERS\$TargetSid")){throw "Профиль пользователя $TargetSid не загружен."}
$officeProcesses=Get-Process WINWORD,EXCEL,VISIO -ErrorAction SilentlyContinue
if($officeProcesses){$names=($officeProcesses|Select-Object -ExpandProperty ProcessName -Unique)-join ", ";throw "Закройте приложения Office ($names) и повторите установку."}
if($OfficeBitness -eq "Auto"){$OfficeBitness=Get-OfficeBitness}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
  $argumentList="-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -DllPath `"$DllPath`" -OfficeBitness $OfficeBitness -TargetSid $TargetSid"
  $process=Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argumentList -Wait -PassThru
  exit $process.ExitCode
}
$sourceDll=(Resolve-Path -LiteralPath $DllPath).Path
$installRoot=Join-Path $env:ProgramFiles "DocFlow\OfficeConnector"
New-Item -ItemType Directory -Force -Path $installRoot|Out-Null
$full=Join-Path $installRoot "DocFlow.OfficeConnector.dll"
Copy-Item -LiteralPath $sourceDll -Destination $full -Force
$frameworkDir=if($OfficeBitness -eq "x86"){"Framework"}else{"Framework64"}
$framework=Join-Path $env:WINDIR "Microsoft.NET\$frameworkDir\v4.0.30319\RegAsm.exe"
if(-not(Test-Path $framework)){throw ".NET Framework RegAsm.exe не найден: $framework"}
& $framework $full /codebase
if($LASTEXITCODE -ne 0){throw "RegAsm завершился с кодом $LASTEXITCODE"}
$entries=@(
 @{App="Word";ProgId="DocFlow.WordAddin";Description="DocFlow Office Connector for Word"},
 @{App="Excel";ProgId="DocFlow.ExcelAddin";Description="DocFlow Office Connector for Excel"},
 @{App="Visio";ProgId="DocFlow.VisioAddin";Description="DocFlow Office Connector for Visio"}
)
foreach($entry in $entries){
 $key="Registry::HKEY_USERS\$TargetSid\Software\Microsoft\Office\$($entry.App)\Addins\$($entry.ProgId)"
 New-Item -Path $key -Force|Out-Null
 New-ItemProperty -Path $key -Name FriendlyName -Value $entry.Description -PropertyType String -Force|Out-Null
 New-ItemProperty -Path $key -Name Description -Value $entry.Description -PropertyType String -Force|Out-Null
 New-ItemProperty -Path $key -Name LoadBehavior -Value 3 -PropertyType DWord -Force|Out-Null
 New-ItemProperty -Path $key -Name CommandLineSafe -Value 0 -PropertyType DWord -Force|Out-Null
}
Write-Host "DocFlow Office Connector зарегистрирован (Office $OfficeBitness)." -ForegroundColor Green
Write-Host "Установка локальная: GitHub и Интернет не используются." -ForegroundColor Gray
