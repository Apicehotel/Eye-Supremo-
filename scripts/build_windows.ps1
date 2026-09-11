$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '== Eye Supremo: build frontend =='
Push-Location frontend
npm ci
npm run build
Pop-Location

Write-Host '== Eye Supremo: build backend executable =='
python -m pip install -r backend/requirements.txt
python -m pip install pyinstaller==6.16.0

$sep = ';'
python -m PyInstaller --noconfirm --clean --onefile --name EyeSupremo `
  --paths backend `
  --add-data "frontend/dist${sep}frontend_dist" `
  --collect-all pydantic `
  --collect-all pydantic_settings `
  backend/desktop.py

Write-Host 'Executable: dist/EyeSupremo.exe'
Write-Host 'Per creare Setup.exe installare Inno Setup 6 e compilare installer/EyeSupremo.iss'
