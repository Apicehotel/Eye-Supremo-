$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '== Eye Supremo: build frontend =='
Push-Location frontend
npm ci
npm run build
Pop-Location

Write-Host '== Eye Supremo: build desktop executable (finestra nativa, no console) =='
python -m pip install -r backend/requirements.txt
python -m pip install pyinstaller==6.16.0

$sep = ';'
# --windowed = nessun CMD nero; UI in WebView2 nativo via pywebview
python -m PyInstaller --noconfirm --clean --onefile --windowed --name EyeSupremo `
  --icon "assets/icons/eye-supremo.ico" `
  --paths backend `
  --add-data "frontend/dist${sep}frontend_dist" `
  --add-data "backend/app/xsd${sep}app/xsd" `
  --add-data "assets/icons/eye-supremo.ico${sep}assets/icons" `
  --collect-all pydantic `
  --collect-all pydantic_settings `
  --collect-all markitdown `
  --collect-all webview `
  --hidden-import app `
  --hidden-import app.main `
  --hidden-import app.routers.api `
  --hidden-import app.routers.auth `
  --hidden-import app.routers.storage `
  --hidden-import app.routers.invoice_builder `
  --hidden-import app.routers.warehouse `
  --hidden-import webview `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols `
  --hidden-import uvicorn.protocols.http `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan `
  --hidden-import uvicorn.lifespan.on `
  backend/desktop.py

Write-Host 'Executable: dist/EyeSupremo.exe (app nativa WebView2)'
Write-Host 'Suite unica: scripts/build_suite.ps1 -> release/EyeSupremo-Setup.exe (+ Ask Fatture)'
