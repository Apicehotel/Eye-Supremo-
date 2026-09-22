# Eye Supremo · applica locazione Supabase (bucket + migration SQL)
# Uso (PowerShell, dalla root del repo):
#   .\applica-locazione-supabase.ps1
#
# Richiede in .env:
#   RANDFATTURE_SUPABASE_URL
#   RANDFATTURE_SUPABASE_SERVICE_KEY
# Opzionale (per eseguire lo SQL senza aprire il dashboard):
#   RANDFATTURE_SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres
#   (Dashboard Supabase → Project Settings → Database → Connection string URI)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Read-DotEnv {
  param([string]$Path)
  $map = @{}
  if (-not (Test-Path $Path)) { return $map }
  Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    $i = $line.IndexOf('=')
    if ($i -lt 1) { return }
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
    $map[$k] = $v
  }
  return $map
}

Write-Host "=== Eye Supremo · locazione Supabase ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path '.env')) {
  if (Test-Path '.env.example') {
    Copy-Item '.env.example' '.env'
    Write-Host "[OK] Creato .env da .env.example — inserisci SERVICE_KEY (e DB_URL se vuoi lo SQL automatico)." -ForegroundColor Yellow
  } else {
    throw ".env / .env.example mancanti"
  }
}

$envMap = Read-DotEnv '.env'
$url = $envMap['RANDFATTURE_SUPABASE_URL']
$key = $envMap['RANDFATTURE_SUPABASE_SERVICE_KEY']
$dbUrl = $envMap['RANDFATTURE_SUPABASE_DB_URL']
$bucket = if ($envMap['RANDFATTURE_SUPABASE_BUCKET']) { $envMap['RANDFATTURE_SUPABASE_BUCKET'] } else { 'eye-invoices' }
$sqlFile = Join-Path $PSScriptRoot 'supabase\migrations\20260922090000_eye_invoices_storage.sql'

if (-not $url) { throw "Manca RANDFATTURE_SUPABASE_URL in .env" }
if (-not $key) { throw "Manca RANDFATTURE_SUPABASE_SERVICE_KEY in .env (service role, Project Settings → API)" }
if (-not (Test-Path $sqlFile)) { throw "Migration non trovata: $sqlFile" }

$headers = @{
  apikey         = $key
  Authorization  = "Bearer $key"
  'Content-Type' = 'application/json'
}

# --- 1) Bucket via Storage API ---------------------------------------------
Write-Host "[1/3] Bucket '$bucket'…"
$bucketBody = @{
  id               = $bucket
  name             = $bucket
  public           = $false
  file_size_limit  = 31457280
  allowed_mime_types = @(
    'application/xml', 'text/xml', 'application/pdf',
    'image/jpeg', 'image/png', 'application/octet-stream'
  )
} | ConvertTo-Json

try {
  Invoke-RestMethod -Method Post -Uri "$url/storage/v1/bucket" -Headers $headers -Body $bucketBody | Out-Null
  Write-Host "      creato." -ForegroundColor Green
} catch {
  $status = $_.Exception.Response.StatusCode.value__
  if ($status -eq 409 -or $status -eq 400) {
    Write-Host "      già presente (ok)." -ForegroundColor Green
  } else {
    Write-Host "      avviso create: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

try {
  $info = Invoke-RestMethod -Method Get -Uri "$url/storage/v1/bucket/$bucket" -Headers $headers
  Write-Host "      verifica: id=$($info.id) public=$($info.public)" -ForegroundColor Green
} catch {
  throw "Bucket non raggiungibile dopo create: $($_.Exception.Message)"
}

# --- 2) Migration SQL ------------------------------------------------------
Write-Host "[2/3] Migration SQL (tabella eye_central_invoice_blobs + policy)…"
$sqlApplied = $false

if ($dbUrl) {
  $psql = Get-Command psql -ErrorAction SilentlyContinue
  if ($psql) {
    & psql $dbUrl -v ON_ERROR_STOP=1 -f $sqlFile
    if ($LASTEXITCODE -ne 0) { throw "psql ha restituito exit $LASTEXITCODE" }
    $sqlApplied = $true
    Write-Host "      applicata con psql." -ForegroundColor Green
  } else {
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if ($npx) {
      npx --yes supabase@latest db query --db-url $dbUrl -f $sqlFile
      if ($LASTEXITCODE -ne 0) { throw "supabase db query exit $LASTEXITCODE" }
      $sqlApplied = $true
      Write-Host "      applicata con supabase CLI." -ForegroundColor Green
    } else {
      Write-Host "      Né psql né npx disponibili: SQL non eseguito automaticamente." -ForegroundColor Yellow
    }
  }
} else {
  Write-Host "      RANDFATTURE_SUPABASE_DB_URL assente → SQL non eseguito da qui." -ForegroundColor Yellow
}

if (-not $sqlApplied) {
  Write-Host ""
  Write-Host "  Apri Supabase → SQL Editor e incolla il file:" -ForegroundColor Cyan
  Write-Host "  $sqlFile"
  Write-Host ""
  try {
    Get-Content -Path $sqlFile -Raw -Encoding UTF8 | Set-Clipboard
    Write-Host "  [OK] SQL copiato negli appunti. Incolla e Run nel SQL Editor." -ForegroundColor Green
  } catch {
    Write-Host "  (Clipboard non disponibile: apri il file a mano.)" -ForegroundColor Yellow
  }
  Write-Host ""
  Write-Host "  Oppure aggiungi in .env la connection string e rilancia:" -ForegroundColor Cyan
  Write-Host '  RANDFATTURE_SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.ooqlfldcrnkudhgjnied.supabase.co:5432/postgres'
}

# --- 3) Verifica indice (REST) ---------------------------------------------
Write-Host "[3/3] Verifica tabella eye_central_invoice_blobs…"
try {
  $probe = @{
    apikey        = $key
    Authorization = "Bearer $key"
    Accept        = 'application/json'
  }
  Invoke-RestMethod -Method Get `
    -Uri "$url/rest/v1/eye_central_invoice_blobs?select=source_hash&limit=1" `
    -Headers $probe | Out-Null
  Write-Host "      tabella OK (raggiungibile con service role)." -ForegroundColor Green
} catch {
  $msg = $_.Exception.Message
  Write-Host "      non verificata: $msg" -ForegroundColor Yellow
  Write-Host "      Se manca la tabella, esegui lo SQL (passo 2) e rilancia." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Fatto. Poi avvia l'app (start.bat) e apri Catalogo centrale / Carica fatture." -ForegroundColor Cyan
Write-Host "Doc: docs\SUPABASE_INVOICES.md"
