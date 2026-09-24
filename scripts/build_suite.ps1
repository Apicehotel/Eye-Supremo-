$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '== Build suite: Eye Supremo + Ask Fatture =='
& "$PSScriptRoot\build_windows.ps1"
& "$PSScriptRoot\build_ask_fatture.ps1"

$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) {
  Write-Host 'Inno Setup 6 non trovato: exe in dist\ pronti, Setup non compilato.'
  Write-Host 'Installa Inno Setup 6 e riesegui, oppure: ISCC.exe installer\EyeSupremo.iss'
  exit 0
}

Write-Host '== Compila installer unico EyeSupremo-Setup.exe =='
& $iscc 'installer\EyeSupremo.iss'
Write-Host 'Pronto: release\EyeSupremo-Setup.exe (Eye Supremo + Ask Fatture)'
