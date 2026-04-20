<#
.SYNOPSIS
    Automazione per il versionamento 3.2 e pacchettizzazione del plugin QGIS_Ledger su Windows.
#>

$ErrorActionPreference = "Stop"

# 1. Configurazione Variabili
$TargetRepo = "C:\Users\SarinoAlfonsoGrande\Documents\plugin\qgis_ledger"
$NewVersion = "3.2"

# Cartella di output e file zip per QGIS
$ParentDir = Split-Path -Path $TargetRepo -Parent
$ReleaseDirName = "qgis_ledger $NewVersion"
$ReleaseDirPath = Join-Path -Path $ParentDir -ChildPath $ReleaseDirName
$ZipFilePath = Join-Path -Path $ParentDir -ChildPath "qgis_ledger_$NewVersion.zip"

Write-Host ">>> Inizio procedura di rilascio per QGIS Ledger v$NewVersion" -ForegroundColor Cyan

# Controllo esistenza directory
if (-not (Test-Path -Path $TargetRepo -PathType Container)) {
    Write-Error "La directory $TargetRepo non esiste."
    exit
}

Set-Location -Path $TargetRepo

# Controllo che sia un repository Git valido
if (-not (Test-Path -Path ".git" -PathType Container)) {
    Write-Error "$TargetRepo non è un repository Git."
    exit
}

# 2. Aggiornamento metadata.txt
$MetadataPath = "metadata.txt"
if (Test-Path -Path $MetadataPath) {
    Write-Host ">>> Aggiornamento versione in metadata.txt..." -ForegroundColor Yellow
    $MetadataContent = Get-Content -Path $MetadataPath
    # Sostituzione tramite Regex della versione
    $MetadataContent = $MetadataContent -replace "^version=.*", "version=$NewVersion"
    Set-Content -Path $MetadataPath -Value $MetadataContent -Encoding UTF8
} else {
    Write-Warning "metadata.txt non trovato. Assicurati che sia la root del plugin."
}

# 3. Operazioni Git: Commit, Branch e Tag
Write-Host ">>> Esecuzione commit su branch master e tagging tramite Git CLI..." -ForegroundColor Yellow

# Verifica che l'eseguibile git sia nel PATH (installato con GitHub Desktop)
try {
    $null = git --version
} catch {
    Write-Error "Comando 'git' non trovato. Assicurati che le utilità da riga di comando di GitHub Desktop siano nel PATH di sistema."
    exit
}

# Assicura di essere su master/main
git checkout master

# Aggiunge e committa
git add metadata.txt
git commit -m "Bump version to $NewVersion"

# Crea/Sovrascrive il tag
git tag -f -a "v$NewVersion" -m "Release plugin versione $NewVersion"

# 4. Generazione della nuova cartella di Rilascio pulita
Write-Host ">>> Generazione della cartella di rilascio pulita in: $ReleaseDirPath" -ForegroundColor Yellow

if (Test-Path -Path $ReleaseDirPath) {
    Remove-Item -Path $ReleaseDirPath -Recurse -Force
}
New-Item -ItemType Directory -Path $ReleaseDirPath | Out-Null

# Esporta i file tracciati nel file temporaneo tar, poi lo estrae nella nuova directory
# Questo ignora la cartella .git e i file di sviluppo non tracciati
$TempTar = Join-Path -Path $ParentDir -ChildPath "temp_export.tar"
git archive --format=tar -o $TempTar HEAD
tar -xf $TempTar -C $ReleaseDirPath
Remove-Item -Path $TempTar -Force

# 5. Creazione pacchetto ZIP per distribuzione
Write-Host ">>> Creazione archivio ZIP: $ZipFilePath" -ForegroundColor Yellow

if (Test-Path -Path $ZipFilePath) {
    Remove-Item -Path $ZipFilePath -Force
}

# Usa la compressione nativa di Windows
Compress-Archive -Path "$ReleaseDirPath\*" -DestinationPath $ZipFilePath

Write-Host ">>> SUCCESSO! Operazioni completate." -ForegroundColor Green
Write-Host " 1. Repository Git taggato (v$NewVersion). Apri GitHub Desktop e clicca 'Push origin' (assicurati di includere i Tag)."
Write-Host " 2. Cartella per QGIS generata: $ReleaseDirPath"
Write-Host " 3. Archivio ZIP pronto: $ZipFilePath"