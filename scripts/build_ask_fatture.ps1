$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '== Ask Fatture: build desktop executable (WebView2, no console) =='
python -m pip install -r ask-fatture/requirements.txt
python -m pip install pyinstaller==6.16.0

$sep = ';'
# --windowed = nessun CMD nero; UI in WebView2 nativo via pywebview
python -m PyInstaller --noconfirm --clean --onefile --windowed --name AskFatture `
  --paths ask-fatture `
  --add-data "ask-fatture/app/static${sep}app/static" `
  --collect-all pydantic `
  --collect-all pydantic_settings `
  --collect-all webview `
  --hidden-import app `
  --hidden-import app.main `
  --hidden-import app.ask `
  --hidden-import app.catalog `
  --hidden-import app.config `
  --hidden-import app.db `
  --hidden-import app.import_xml `
  --hidden-import app.normalize `
  --hidden-import app.version `
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
  ask-fatture/desktop.py

Write-Host 'Executable: dist/AskFatture.exe (app nativa WebView2)'
Write-Host 'Per Setup.exe: Inno Setup 6 → installer/AskFatture.iss'
