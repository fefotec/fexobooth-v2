param(
    [string]$InstallDir = "C:\FexoBooth"
)

# ============================================================
#  FexoBooth - Uhrzeit richtig halten (2.4.75, 02.11.2026)
# ============================================================
#  Problem: Mehrere Boxen gingen 1-12 Stunden falsch (Log-Abgleich 02.11.2026:
#  Box 002 ~9 h nach, 102 ~12 h nach, 206 ~1,75 h vor, 210/218 ~1 h vor).
#  Falsche Box-Zeit macht Logs, Dateinamen und Event-Statistik unbrauchbar.
#  Beim Kunden haben die Boxen KEIN Internet - und das bleibt so.
#
#  Was dieses Script tut (laeuft als SYSTEM in der Boot-/Login-Aufgabe
#  "FexoBooth Windows Update Lockdown", wird von dort ohne Warten gestartet):
#    1. Zeitzone "W. Europe Standard Time" mit automatischer Sommerzeit
#       (alle Einsatzlaender DE/AT/FR/NL/BE liegen in MEZ/MESZ).
#    2. Windows-Zeitdienst an: holt die Zeit per NTP, sobald Internet da ist
#       (= im Firmen-WLAN), danach stuendlich. Grosse Korrekturen erlaubt
#       (Standard: max. 48 h - nach leerem Akku liegt die Uhr evtl. Jahre daneben).
#    3. Sperre: Nach jedem erfolgreichen Abgleich wird die Zeit gemerkt. Steht
#       die Uhr beim naechsten Start VOR diesem Zeitpunkt (Tablet war ganz leer),
#       wird sie auf die gemerkte Zeit vorgestellt. Ungefaehr richtig ist besser
#       als ein Datum aus 2016 - und die Uhr springt nie rueckwaerts.
#
#  Log: <InstallDir>\logs\uhrzeit.log  (kommt mit dem Log-Upload mit)
#  Exit-Code ist IMMER 0.
# ============================================================

$ErrorActionPreference = "Continue"

$LogDir = Join-Path $InstallDir "logs"
$LogFile = Join-Path $LogDir "uhrzeit.log"
$StateDir = Join-Path $env:ProgramData "FexoBox"
$StateFile = Join-Path $StateDir "uhrzeit_letzte_gute.txt"
$TimeZoneId = "W. Europe Standard Time"
$NtpPeers = "time.windows.com,0x9 ptbtime1.ptb.de,0x9 pool.ntp.org,0x9"
$ResyncTries = 6
$ResyncPauseSec = 20

function Write-TimeLog {
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
        # Log klein halten (nur die letzten ~400 Zeilen behalten)
        $all = Get-Content -Path $LogFile -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($all.Count -gt 600) {
            $all | Select-Object -Last 400 | Set-Content -Path $LogFile -Encoding UTF8
        }
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

function Get-UnixNow {
    return [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
}

function Set-DwordValue {
    # $Value als int64: In PowerShell 5.1 ist das Literal 0xFFFFFFFF = -1 (int32),
    # ein [uint32]-Parameter wuerde daran scheitern. Gespeichert wird das
    # 32-Bit-Muster als int32 (Registry liefert es genauso zurueck).
    param([string]$Path, [string]$Name, [int64]$Value)
    $bits = [BitConverter]::ToInt32([BitConverter]::GetBytes([int64]($Value -band 0xFFFFFFFFL)), 0)
    try {
        if (-not (Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
        $current = (Get-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue).$Name
        # Vergleich ueber das 32-Bit-Muster: Die Registry liefert 0xFFFFFFFF je nach
        # Weg als -1 ODER als 4294967295 (Box 018, 02.11.2026: [int32]-Cast scheiterte).
        if ($null -eq $current -or ([int64]$current -band 0xFFFFFFFFL) -ne ([int64]$bits -band 0xFFFFFFFFL)) {
            New-ItemProperty -Path $Path -Name $Name -PropertyType DWord -Value $bits -Force | Out-Null
            Write-TimeLog "Gesetzt: $Name = $Value (vorher: $current)"
            return $true
        }
    } catch {
        Write-TimeLog "Wert $Name konnte nicht gesetzt werden: $($_.Exception.Message)" "WARN"
    }
    return $false
}

Write-TimeLog "Uhrzeit-Pruefung startet (Benutzer=$env:USERNAME, Uhr zeigt $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))"

if (-not (Test-Admin)) {
    Write-TimeLog "Keine Admin-Rechte - nichts geaendert (laeuft normal als SYSTEM aus der Boot-Aufgabe)" "ERROR"
    exit 0
}

# ---------- 3. Sperre: Uhr nie vor die letzte gute Zeit ----------
try {
    if (Test-Path $StateFile) {
        $lastGood = [int64]((Get-Content -Path $StateFile -ErrorAction Stop | Select-Object -First 1).Trim())
        $now = Get-UnixNow
        if ($lastGood -gt 1700000000 -and $now -lt ($lastGood - 300)) {
            $target = [DateTimeOffset]::FromUnixTimeSeconds($lastGood).LocalDateTime
            Set-Date -Date $target | Out-Null
            Write-TimeLog ("Uhr lag {0:N1} h VOR der letzten guten Zeit (Tablet-Akku leer?) -> vorgestellt auf {1:yyyy-MM-dd HH:mm:ss}" -f (($lastGood - $now) / 3600.0), $target) "WARN"
        } else {
            Write-TimeLog ("Sperre ok: letzte gute Zeit {0:yyyy-MM-dd HH:mm:ss}" -f [DateTimeOffset]::FromUnixTimeSeconds($lastGood).LocalDateTime)
        }
    } else {
        Write-TimeLog "Sperre: noch keine gute Zeit gemerkt (erster Abgleich steht aus)"
    }
} catch {
    Write-TimeLog "Sperre nicht pruefbar: $($_.Exception.Message)" "WARN"
}

# ---------- 1. Zeitzone + Sommerzeit ----------
try {
    $tz = (& tzutil.exe /g 2>$null)
    if ($tz -ne $TimeZoneId) {
        & tzutil.exe /s $TimeZoneId | Out-Null
        Write-TimeLog "Zeitzone gesetzt: $TimeZoneId (vorher: $tz)"
    } else {
        Write-TimeLog "Zeitzone bereits richtig: $tz"
    }
} catch {
    Write-TimeLog "Zeitzone nicht setzbar: $($_.Exception.Message)" "WARN"
}
Set-DwordValue -Path "HKLM:\SYSTEM\CurrentControlSet\Control\TimeZoneInformation" -Name "DynamicDaylightTimeDisabled" -Value 0 | Out-Null

# ---------- 2. Windows-Zeitdienst ----------
$w32 = "HKLM:\SYSTEM\CurrentControlSet\Services\W32Time"
Set-DwordValue -Path "$w32\TimeProviders\NtpClient" -Name "SpecialPollInterval" -Value 3600 | Out-Null
Set-DwordValue -Path "$w32\Config" -Name "MaxPosPhaseCorrection" -Value 0xFFFFFFFF | Out-Null
Set-DwordValue -Path "$w32\Config" -Name "MaxNegPhaseCorrection" -Value 0xFFFFFFFF | Out-Null
try {
    & sc.exe config w32time start= auto | Out-Null
    $svc = Get-Service -Name "w32time" -ErrorAction Stop
    if ($svc.Status -ne "Running") {
        Start-Service -Name "w32time" -ErrorAction Stop
        Write-TimeLog "Zeitdienst gestartet"
    }
    & w32tm.exe /config "/manualpeerlist:$NtpPeers" /syncfromflags:manual /update | Out-Null
    Write-TimeLog "Zeitdienst konfiguriert (Server: $NtpPeers, stuendlich)"
} catch {
    Write-TimeLog "Zeitdienst nicht einrichtbar: $($_.Exception.Message)" "WARN"
}

# ---------- Abgleich (nur mit Internet, also im Firmen-WLAN) ----------
$synced = $false
for ($i = 1; $i -le $ResyncTries; $i++) {
    $before = Get-UnixNow
    $out = (& w32tm.exe /resync /force 2>&1) -join " "
    if ($LASTEXITCODE -eq 0) {
        $delta = (Get-UnixNow) - $before
        Write-TimeLog ("Zeit abgeglichen (Versuch {0}), Korrektur ca. {1} s" -f $i, $delta)
        $synced = $true
        break
    }
    if ($i -eq 1) {
        Write-TimeLog "Kein Abgleich moeglich (kein Internet?) - versuche noch $($ResyncTries - 1)x: $($out.Trim())"
    }
    Start-Sleep -Seconds $ResyncPauseSec
}

if ($synced) {
    try {
        if (-not (Test-Path $StateDir)) { New-Item -Path $StateDir -ItemType Directory -Force | Out-Null }
        Set-Content -Path $StateFile -Value (Get-UnixNow) -Encoding ASCII
        Write-TimeLog "Gute Zeit gemerkt: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    } catch {
        Write-TimeLog "Gute Zeit konnte nicht gemerkt werden: $($_.Exception.Message)" "WARN"
    }
} else {
    Write-TimeLog "Ohne Internet kein Abgleich (normal beim Kunden) - Uhr bleibt: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

Write-TimeLog "Uhrzeit-Pruefung fertig"
exit 0
