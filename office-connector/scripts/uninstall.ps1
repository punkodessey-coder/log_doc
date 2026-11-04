$ErrorActionPreference = "Continue"
$entries = @(
  @{ App="Word"; ProgId="DocFlow.WordAddin" },
  @{ App="Excel"; ProgId="DocFlow.ExcelAddin" },
  @{ App="Visio"; ProgId="DocFlow.VisioAddin" }
)
foreach ($entry in $entries) {
  Remove-Item -Path "HKCU:\Software\Microsoft\Office\$($entry.App)\Addins\$($entry.ProgId)" -Recurse -Force
}
Write-Host "Записи надстроек удалены. DLL можно удалить вручную после закрытия Office."
