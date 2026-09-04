param(
    [string]$InstallDir = "C:\FexoBooth"
)

# ============================================================
#  FexoBooth - Hotspot-Leerlauf-Abschaltung von Windows deaktivieren (2.4.65)
# ============================================================
#  Windows schaltet den mobilen Hotspot von selbst ab, wenn eine Weile kein
#  Geraet verbunden ist (Standard: 5 Minuten) - und zusaetzlich, wenn die
#  geteilte Verbindung kein Internet hat. Beides trifft eine Feier mitten
#  drin: Gaeste holen am Anfang Fotos, dann ist Ruhe, danach kommt niemand
#  mehr ins WLAN ("der QR-Code geht nicht"). Belegt am 04.09.2026 auf Box 155
#  (10:04 Hotspot AN, 11:26 aus, ohne Zutun der Software).
#
#  Dieses Script setzt die zwei Schalter des Windows-Dienstes "Mobiler
#  Hotspot" (icssvc) dauerhaft auf AUS. Es braucht Admin-Rechte und laeuft
#  deshalb NUR an zwei Stellen:
#    1. im Installer als Pflicht-Schritt (der Installer laeuft als Admin)
#    2. in der Boot-/Login-Aufgabe "FexoBooth Windows Update Lockdown"
#       (laeuft als SYSTEM) - damit der Wert auch bleibt, falls Windows ihn
#       je zuruecksetzt.
#  Die Box-Software selbst liest die Werte nur (Kiosk-Konto) und schreibt sie
#  ins Log (Hotspot-Waechter / NETZ-BILANZ).
#
#  Log: <InstallDir>\logs\hotspot_keepalive.log
#  Exit-Code ist IMMER 0: Der Installer darf daran nie scheitern.
# ============================================================

$ErrorActionPreference = "Continue"

$LogDir = Join-Path $InstallDir "logs"
$LogFile = Join-Path $LogDir "hotspot_keepalive.log"

function Write-KeepaliveLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $line = "{0} | {1} | {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    try {
        if (-not (Test-Path $LogDir)) {
            New-Item -Path $LogDir -ItemType Directory -Force | Out-Null
        }
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch {
        Write-Host "Logging failed: $($_.Exception.Message)"
    }
}

function Test-Admin {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

$settingsPath = "HKLM:\SYSTEM\CurrentControlSet\Services\icssvc\Settings"
$valueNames = @("PeerlessTimeoutEnabled", "PublicConnectionTimeoutEnabled")

Write-KeepaliveLog "Hotspot-Keepalive startet (InstallDir=$InstallDir, Benutzer=$env:USERNAME)"

if (-not (Test-Admin)) {
    Write-KeepaliveLog "Keine Admin-Rechte - Werte koennen nicht gesetzt werden (Installer/Boot-Aufgabe erneut laufen lassen)" "ERROR"
    exit 0
}

$changed = $false

try {
    if (-not (Test-Path $settingsPath)) {
        New-Item -Path $settingsPath -Force | Out-Null
        Write-KeepaliveLog "Schluessel angelegt: $settingsPath"
    }
} catch {
    Write-KeepaliveLog "Schluessel konnte nicht angelegt werden: $($_.Exception.Message)" "ERROR"
    exit 0
}

foreach ($name in $valueNames) {
    try {
        $current = $null
        $item = Get-ItemProperty -Path $settingsPath -Name $name -ErrorAction SilentlyContinue
        if ($null -ne $item) {
            $current = $item.$name
        }
        if ($null -eq $current) {
            New-ItemProperty -Path $settingsPath -Name $name -PropertyType DWord -Value 0 -Force | Out-Null
            $changed = $true
            Write-KeepaliveLog "Gesetzt: $name = 0 (vorher: nicht vorhanden = Abschaltung AKTIV)"
        } elseif ([int]$current -ne 0) {
            Set-ItemProperty -Path $settingsPath -Name $name -Value 0 -Type DWord -Force
            $changed = $true
            Write-KeepaliveLog "Gesetzt: $name = 0 (vorher: $current)"
        } else {
            Write-KeepaliveLog "Bereits richtig: $name = 0"
        }
    } catch {
        Write-KeepaliveLog "Wert $name konnte nicht gesetzt werden: $($_.Exception.Message)" "ERROR"
    }
}

# Nachlesen - das ist der Beweis im Log.
$pruefung = @()
foreach ($name in $valueNames) {
    $item = Get-ItemProperty -Path $settingsPath -Name $name -ErrorAction SilentlyContinue
    if ($null -ne $item) { $pruefung += "$name=$($item.$name)" } else { $pruefung += "$name=FEHLT" }
}
Write-KeepaliveLog ("Pruefung: " + ($pruefung -join ", "))

# Der Dienst liest die Werte beim Start. Nur neu starten, wenn wirklich etwas
# geaendert wurde - ein Neustart wuerde einen laufenden Hotspot kurz beenden.
if ($changed) {
    try {
        $svc = Get-Service -Name "icssvc" -ErrorAction SilentlyContinue
        if ($null -ne $svc -and $svc.Status -eq "Running") {
            Restart-Service -Name "icssvc" -Force -ErrorAction Stop
            Write-KeepaliveLog "Dienst 'Mobiler Hotspot' (icssvc) neu gestartet, damit die Werte greifen"
        } else {
            Write-KeepaliveLog "Dienst icssvc laeuft nicht - Werte greifen beim naechsten Start"
        }
    } catch {
        Write-KeepaliveLog "Dienst icssvc konnte nicht neu gestartet werden (greift nach dem naechsten Boot): $($_.Exception.Message)" "WARN"
    }
} else {
    Write-KeepaliveLog "Nichts geaendert - kein Dienst-Neustart noetig"
}

Write-KeepaliveLog "Hotspot-Keepalive fertig"
exit 0
