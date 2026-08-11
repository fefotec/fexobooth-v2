# ============================================
# FEXOBOOTH - FIRMEN-WLAN EINRICHTEN (2.4.22)
# ============================================
# Laeuft automatisch als Pflicht-Schritt im Installer (elevated, silent).
# Legt das "fexon WLAN"-Profil mit Klartext-Schluessel frisch an
# (funktioniert auf JEDER Box, unabhaengig vom Klon-Image) und stellt die
# zwei entscheidenden Einstellungen sicher:
#   - automatisch verbinden = AN
#   - MAC-Randomisierung   = AUS  (Kernursache der Anmelde-Probleme)
# Kein Neustart noetig. Log: <InstallDir>\logs\company_wlan_setup.log
# ============================================

param(
    [string]$InstallDir = "C:\FexoBooth"
)

$Ssid = "fexon WLAN"
$Passphrase = "68045370152863146883"

$LogDir = Join-Path $InstallDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = Join-Path $LogDir "company_wlan_setup.log"

function Write-Log([string]$Message, [string]$Level = "INFO") {
    $line = "{0} | {1} | {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

Write-Log "Firmen-WLAN-Setup startet (InstallDir=$InstallDir)"

$ssidHex = ([System.Text.Encoding]::UTF8.GetBytes($Ssid) | ForEach-Object { $_.ToString("X2") }) -join ""

$profileXml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>$Ssid</name>
    <SSIDConfig>
        <SSID>
            <hex>$ssidHex</hex>
            <name>$Ssid</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>$Passphrase</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
    <MacRandomization xmlns="http://www.microsoft.com/networking/WLAN/profile/v3">
        <enableRandomization>false</enableRandomization>
    </MacRandomization>
</WLANProfile>
"@

$profilePath = Join-Path $env:TEMP "fexobooth_company_wlan.xml"

try {
    Set-Content -Path $profilePath -Value $profileXml -Encoding utf8

    $addResult = netsh wlan add profile filename="$profilePath" user=all 2>&1
    Write-Log "Profil-Import: $addResult"

    netsh wlan connect name="$Ssid" 2>&1 | Out-Null
    Write-Log "Verbindungsversuch mit '$Ssid' angestossen"

    # Bis zu 20 Sekunden auf die Verbindung warten (best effort; wenn das
    # WLAN nicht in Reichweite ist, ist das kein Fehler)
    $connected = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 2
        $interfaces = netsh wlan show interfaces 2>&1 | Out-String
        if ($interfaces -match [regex]::Escape($Ssid)) { $connected = $true; break }
    }

    if ($connected) {
        Write-Log "Mit '$Ssid' verbunden - Setup erfolgreich"
    } else {
        Write-Log "Profil eingerichtet, aktuell keine Verbindung (WLAN evtl. nicht in Reichweite) - verbindet sich automatisch, sobald sichtbar" "WARN"
    }
} catch {
    Write-Log "Setup fehlgeschlagen: $($_.Exception.Message)" "ERROR"
} finally {
    Remove-Item -Path $profilePath -Force -ErrorAction SilentlyContinue
}
