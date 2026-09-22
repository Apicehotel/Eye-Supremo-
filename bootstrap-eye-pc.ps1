# Bootstrap Eye Supremo sul PC (senza avere già il repo)
# Incolla in PowerShell (anche da system32) e premi Invio:
#
#   irm https://raw.githubusercontent.com/Apicehotel/Eye-Supremo-/main/bootstrap-eye-pc.ps1 | iex
#
# Oppure salva questo file e:  powershell -ExecutionPolicy Bypass -File .\bootstrap-eye-pc.ps1

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/Apicehotel/Eye-Supremo-.git'
$Target = Join-Path $env:USERPROFILE 'Eye-Supremo-'

Write-Host ""
Write-Host "=== Eye Supremo · setup PC ===" -ForegroundColor Cyan
Write-Host "Cartella: $Target"
Write-Host ""

# --- Git ---
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
  Write-Host "Git non trovato. Installalo da https://git-scm.com/download/win e rilancia." -ForegroundColor Red
  exit 1
}

if (-not (Test-Path (Join-Path $Target '.git'))) {
  Write-Host "[1/4] Clone del repository…"
  if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
  git clone --branch main --depth 1 $RepoUrl $Target
} else {
  Write-Host "[1/4] Repo già presente → git pull"
  Push-Location $Target
  git checkout main
  git pull origin main
  Pop-Location
}

Set-Location $Target

# --- Chiavi (solo queste le chiediamo a te) ---
Write-Host ""
Write-Host "[2/4] Chiavi Supabase" -ForegroundColor Cyan
Write-Host "Apri: https://supabase.com/dashboard/project/ooqlfldcrnkudhgjnied/settings/api"
Write-Host "Copia la chiave service_role (Reveal), poi incollala qui."
Write-Host ""

$serviceKey = Read-Host "Incolla SERVICE_ROLE key"
if (-not $serviceKey -or $serviceKey.Length -lt 20) {
  throw "Service key mancante o troppo corta."
}

$centralPin = Read-Host "Incolla PIN MultiHotel di sviluppatore (catalogo ~20k; Invio per saltare)"
$anonKey = Read-Host "Incolla ANON/publishable key (opzionale, Invio per saltare)"

# --- Scrivi .env ---
Write-Host "[3/4] Scrivo .env in $Target"
$envLines = @(
  '# Generato da bootstrap-eye-pc.ps1',
  'RANDFATTURE_OLLAMA_URL=http://127.0.0.1:11434',
  'RANDFATTURE_CHAT_MODEL=qwen3:4b',
  'RANDFATTURE_EMBEDDING_MODEL=nomic-embed-text',
  'RANDFATTURE_SUPABASE_URL=https://ooqlfldcrnkudhgjnied.supabase.co',
  "RANDFATTURE_SUPABASE_SERVICE_KEY=$serviceKey",
  "RANDFATTURE_SUPABASE_ANON_KEY=$anonKey",
  'RANDFATTURE_SUPABASE_BUCKET=eye-invoices',
  'RANDFATTURE_SUPABASE_STORAGE_ROOT=invoices',
  'RANDFATTURE_SUPABASE_CENTRAL_USERNAME=sviluppatore',
  "RANDFATTURE_SUPABASE_CENTRAL_PIN=$centralPin"
)
$envLines -join "`r`n" | Set-Content -Path (Join-Path $Target '.env') -Encoding UTF8
Write-Host "      .env creato." -ForegroundColor Green

# --- Dipendenze ---
Write-Host "[4/4] Installazione (setup.bat)…"
if (Test-Path (Join-Path $Target 'setup.bat')) {
  cmd /c "cd /d `"$Target`" && setup.bat"
} else {
  Write-Host "setup.bat non trovato — apri la cartella e lancialo a mano." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "FATTO." -ForegroundColor Green
Write-Host "Cartella: $Target"
Write-Host "File chiavi: $Target\.env"
Write-Host "Avvio: doppio clic su start.bat (nella stessa cartella)"
Write-Host "Poi in app: Catalogo centrale / Carica fatture"
Write-Host ""
explorer $Target
