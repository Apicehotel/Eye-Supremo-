$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '== Eye Supremo: build frontend =='
Push-Location frontend
try { npm ci } catch { Write-Warning 'npm ci non riuscito (file nativo in uso); uso le dipendenze già installate.' }
npm run build
Pop-Location

Write-Host '== Eye Supremo: build desktop executable (finestra nativa WebView2, no browser) =='
python -m pip install -r backend/requirements.txt
python -m pip install pyinstaller==6.16.0

$sep = ';'
$icon = Join-Path $Root 'installer\assets\eye-supremo.ico'
# --windowed = nessun CMD nero; UI in WebView2 nativo via pywebview (non apre Chrome/Edge)
python -m PyInstaller --noconfirm --clean --onefile --windowed --name EyeSupremo `
  --paths backend `
  --icon $icon `
  --add-data "frontend/dist${sep}frontend_dist" `
  --add-data "installer/assets/eye-supremo.ico${sep}." `
  --collect-all pydantic `
  --collect-all pydantic_settings `
  --collect-all webview `
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

Write-Host 'Executable: dist/EyeSupremo.exe (app nativa WebView2, non pagina web)'
Write-Host 'Per creare Setup.exe installare Inno Setup 6 e compilare installer/EyeSupremo.iss'
