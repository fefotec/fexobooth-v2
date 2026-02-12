# ============================================
# FexoBooth - Clonezilla Download Script
# ============================================
# Laedt die aktuelle Clonezilla Live Version herunter.
# Aufruf: powershell -ExecutionPolicy Bypass -File download_clonezilla.ps1 -OutputDir ".\downloads"
# ============================================

param(
    [string]$OutputDir = ".\downloads"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host ""
Write-Host "============================================"
Write-Host "  Clonezilla Live herunterladen"
Write-Host "============================================"
Write-Host ""

# Output-Verzeichnis erstellen
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Clonezilla Download-Seite abfragen um aktuelle Version zu finden
Write-Host "Suche aktuelle Clonezilla-Version..."

try {
    # Versuche die stabile Release-Seite zu parsen
    $releasePage = Invoke-WebRequest -Uri "https://clonezilla.org/downloads/download.php?branch=stable" -UseBasicParsing -TimeoutSec 30

    # Alternative: Direkt eine bekannte stabile Version verwenden
    # Falls die Webseite sich aendert, hier die Version anpassen:
    $fallbackVersion = "3.3.0-33"
    $fallbackUrl = "https://sourceforge.net/projects/clonezilla/files/clonezilla_live_stable/$fallbackVersion/clonezilla-live-$fallbackVersion-amd64.zip/download"

} catch {
    Write-Host "Webseite nicht erreichbar, verwende bekannte Version..."
}

# Download-URL (SourceForge)
$version = $fallbackVersion
$fileName = "clonezilla-live-$version-amd64.zip"
$downloadUrl = $fallbackUrl
$outputPath = Join-Path $OutputDir $fileName

# Pruefe ob bereits vorhanden
if (Test-Path $outputPath) {
    Write-Host "[OK] $fileName bereits vorhanden in $OutputDir"
    Write-Host "     Loesche die Datei und fuehre das Script erneut aus fuer einen neuen Download."
    exit 0
}

Write-Host ""
Write-Host "Version:  $version"
Write-Host "Datei:    $fileName"
Write-Host "Ziel:     $outputPath"
Write-Host ""
Write-Host "Lade herunter (~500 MB, bitte warten)..."
Write-Host ""

try {
    # SourceForge Redirect folgen
    $webClient = New-Object System.Net.WebClient
    $webClient.Headers.Add("User-Agent", "FexoBooth-Deployment/1.0")

    # Fortschrittsanzeige
    $lastPercent = 0
    Register-ObjectEvent -InputObject $webClient -EventName DownloadProgressChanged -Action {
        $percent = $EventArgs.ProgressPercentage
        if ($percent -ne $script:lastPercent -and $percent % 5 -eq 0) {
            $mbDone = [math]::Round($EventArgs.BytesReceived / 1MB, 0)
            $mbTotal = [math]::Round($EventArgs.TotalBytesToReceive / 1MB, 0)
            Write-Host "  $percent% ($mbDone / $mbTotal MB)"
            $script:lastPercent = $percent
        }
    } | Out-Null

    # Download starten
    $webClient.DownloadFile($downloadUrl, $outputPath)
    $webClient.Dispose()

    $fileSize = [math]::Round((Get-Item $outputPath).Length / 1MB, 1)
    Write-Host ""
    Write-Host "[OK] Download abgeschlossen: $fileName ($fileSize MB)"
    Write-Host "     Gespeichert in: $outputPath"

} catch {
    Write-Host ""
    Write-Host "FEHLER beim Download: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "Bitte manuell herunterladen:"
    Write-Host "  1. Oeffne: https://clonezilla.org/downloads.php"
    Write-Host "  2. Waehle: stable, amd64, zip"
    Write-Host "  3. Speichere die ZIP-Datei in: $OutputDir"
    Write-Host ""

    # Unvollstaendige Datei loeschen
    if (Test-Path $outputPath) {
        Remove-Item $outputPath -Force
    }
    exit 1
}

Write-Host ""
Write-Host "Naechster Schritt: Rufus starten und Clonezilla auf USB-Stick schreiben."
Write-Host ""
