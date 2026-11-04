param([string]$DllPath,[ValidateSet("Auto","x86","x64")][string]$OfficeBitness="Auto",[string]$TargetSid)
$ErrorActionPreference="Stop"
if([string]::IsNullOrWhiteSpace($TargetSid)){$TargetSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value}
if(-not(Test-Path "Registry::HKEY_USERS\$TargetSid")){throw "Профиль пользователя $TargetSid не загружен."}
$officeProcesses=Get-Process WINWORD,EXCEL,VISIO -ErrorAction SilentlyContinue
if($officeProcesses){$names=($officeProcesses|Select-Object -ExpandProperty ProcessName -Unique)-join ", ";throw "Закройте приложения Office ($names) и повторите удаление."}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
 $argumentList=@("-NoProfile","-ExecutionPolicy","Bypass","-File",$PSCommandPath,"-DllPath",$DllPath,"-OfficeBitness",$OfficeBitness,"-TargetSid",$TargetSid)
 $process=Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argumentList -Wait -PassThru
 exit $process.ExitCode
}
$entries=@(
 @{App="Word";ProgId="DocFlow.WordAddin";Clsid="{B7D1C64C-84AE-4A67-9DB1-3B5C43E30101}"},
 @{App="Excel";ProgId="DocFlow.ExcelAddin";Clsid="{B7D1C64C-84AE-4A67-9DB1-3B5C43E30102}"},
 @{App="Visio";ProgId="DocFlow.VisioAddin";Clsid="{B7D1C64C-84AE-4A67-9DB1-3B5C43E30103}"}
)
foreach($entry in $entries){Remove-Item -LiteralPath "Registry::HKEY_USERS\$TargetSid\Software\Microsoft\Office\$($entry.App)\Addins\$($entry.ProgId)" -Recurse -Force -ErrorAction SilentlyContinue}
$regAsmPaths=@((Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\RegAsm.exe"),(Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"))
if(-not [string]::IsNullOrWhiteSpace($DllPath) -and (Test-Path -LiteralPath $DllPath)){
 $fullDll=(Resolve-Path -LiteralPath $DllPath).Path
 foreach($regAsm in $regAsmPaths){if(Test-Path $regAsm){& $regAsm $fullDll /unregister;if($LASTEXITCODE -ne 0){Write-Warning "RegAsm returned $LASTEXITCODE ($regAsm)"}}}
}
foreach($entry in $entries){
 foreach($root in @("Registry::HKEY_USERS\$TargetSid\Software\Classes","Registry::HKEY_LOCAL_MACHINE\Software\Classes","Registry::HKEY_LOCAL_MACHINE\Software\Classes\WOW6432Node")){
  Remove-Item -LiteralPath (Join-Path $root $entry.ProgId) -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $root "CLSID\$($entry.Clsid)") -Recurse -Force -ErrorAction SilentlyContinue
 }
}
$installRoot=Join-Path $env:ProgramFiles "DocFlow\OfficeConnector"
Remove-Item -LiteralPath $installRoot -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "DocFlow удалён из Word, Excel и Visio. Данные сервера не затронуты." -ForegroundColor Green
