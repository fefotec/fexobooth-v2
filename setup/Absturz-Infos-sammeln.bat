@echo off
rem ============================================================
rem  FexoBooth - Absturz-Infos sammeln  (2.4.30)
rem ============================================================
rem  Doppelklick auf dieser Datei genuegt. Sie sammelt alles, was
rem  Windows ueber Abstuerze der Box gespeichert hat, und legt es
rem  als Textdatei in C:\FexoBooth\logs ab.
rem
rem  Danach nur noch: den kompletten Ordner C:\FexoBooth\logs auf
rem  den USB-Stick kopieren und an Claude schicken.
rem
rem  HINWEIS: Die Datei ist bewusst ASCII (keine Umlaute) - der
rem  PowerShell-Teil unten wird aus dieser Datei selbst gelesen,
rem  Sonderzeichen wuerden dabei kaputtgehen.
rem ============================================================
title FexoBooth - Absturz-Infos sammeln
color 0B
echo.
echo   ===============================================
echo    FexoBooth - Absturz-Infos sammeln
echo   ===============================================
echo.
echo   Bitte einen Moment warten...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=[IO.File]::ReadAllText('%~f0'); $m='#'+'PSCODE#'; $i=$c.IndexOf($m); if($i -lt 0){Write-Host 'FEHLER: Script-Teil nicht gefunden'; exit 1}; Invoke-Expression $c.Substring($i+$m.Length)"

echo.
echo   Fenster kann jetzt geschlossen werden.
echo.
pause
exit /b

#PSCODE#
$ErrorActionPreference = 'SilentlyContinue'

$logDir = 'C:\FexoBooth\logs'
if (-not (Test-Path $logDir)) {
    try { New-Item -ItemType Directory -Path $logDir -Force | Out-Null } catch { $logDir = $env:TEMP }
}
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out   = Join-Path $logDir ("windows-absturz_" + $stamp + ".txt")

$L = New-Object System.Collections.Generic.List[string]
function Zeile([string]$t) { $L.Add($t) | Out-Null }
function Titel([string]$t) { Zeile ''; Zeile ('=' * 70); Zeile "  $t"; Zeile ('=' * 70) }

# ---------------------------------------------------------------
# 1. Kopf
# ---------------------------------------------------------------
Titel 'FEXOBOOTH - ABSTURZ-INFOS'
Zeile ("Erstellt am     : " + (Get-Date -Format 'dd.MM.yyyy HH:mm:ss'))
Zeile ("Computer        : " + $env:COMPUTERNAME)
Zeile ("Benutzer        : " + $env:USERNAME)
try {
    $os = Get-CimInstance Win32_OperatingSystem
    Zeile ("Windows         : " + $os.Caption + " (Build " + $os.BuildNumber + ")")
    Zeile ("Letzter Neustart: " + $os.LastBootUpTime)
} catch { Zeile 'Windows         : (nicht lesbar)' }

# Box-ID + Version aus der Installation
try {
    $cfg = Get-Content 'C:\FexoBooth\config.json' -Raw | ConvertFrom-Json
    Zeile ("Box-ID          : " + $cfg.box_id)
} catch { Zeile 'Box-ID          : (config.json nicht lesbar)' }
try {
    $exe = Get-Item 'C:\FexoBooth\fexobooth.exe'
    Zeile ("EXE geaendert   : " + $exe.LastWriteTime)
} catch { }

$istAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Zeile ("Adminrechte     : " + $(if ($istAdmin) { 'ja' } else { 'NEIN - einige Teile werden uebersprungen' }))

# ---------------------------------------------------------------
# 2. Windows-Absturzmeldungen zu fexobooth
# ---------------------------------------------------------------
Titel 'WINDOWS-ABSTURZMELDUNGEN (fexobooth, letzte 21 Tage)'
$gefunden = 0
try {
    $ev = Get-WinEvent -FilterHashtable @{
        LogName      = 'Application'
        ProviderName = 'Application Error', 'Application Hang', '.NET Runtime', 'Windows Error Reporting'
        StartTime    = (Get-Date).AddDays(-21)
    } -MaxEvents 200
    foreach ($e in $ev) {
        if ($e.Message -like '*fexobooth*') {
            $gefunden++
            Zeile ''
            Zeile ("--- " + $e.TimeCreated + " | " + $e.ProviderName + " | Id " + $e.Id + " ---")
            foreach ($z in ($e.Message -split "`r?`n")) { if ($z.Trim()) { Zeile ("    " + $z.Trim()) } }
        }
    }
} catch { Zeile ("Ereignisprotokoll nicht lesbar: " + $_.Exception.Message) }
if ($gefunden -eq 0) { Zeile 'KEINE Absturzmeldung zu fexobooth gefunden.' }
else { Zeile ''; Zeile ("Summe: " + $gefunden + " Meldung(en)") }

# ---------------------------------------------------------------
# 3. Alle Absturzmeldungen (falls der Name abweicht)
# ---------------------------------------------------------------
Titel 'ALLE ABSTURZMELDUNGEN (letzte 7 Tage, Kurzform)'
try {
    $alle = Get-WinEvent -FilterHashtable @{
        LogName      = 'Application'
        ProviderName = 'Application Error', 'Application Hang'
        StartTime    = (Get-Date).AddDays(-7)
    } -MaxEvents 60
    if ($alle) {
        foreach ($e in $alle) {
            $kurz = ($e.Message -split "`r?`n")[0].Trim()
            $modul = ($e.Message -split "`r?`n" | Where-Object { $_ -match 'Modul' } | Select-Object -First 1)
            Zeile ("  " + $e.TimeCreated + "  " + $kurz)
            if ($modul) { Zeile ("      " + $modul.Trim()) }
        }
    } else { Zeile 'Keine.' }
} catch { Zeile 'Nicht lesbar.' }

# ---------------------------------------------------------------
# 4. Windows-Fehlerberichte (WER)
# ---------------------------------------------------------------
Titel 'WINDOWS-FEHLERBERICHTE (WER)'
$werPfade = @(
    'C:\ProgramData\Microsoft\Windows\WER\ReportArchive',
    'C:\ProgramData\Microsoft\Windows\WER\ReportQueue',
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\WER\ReportArchive'),
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\WER\ReportQueue')
)
$werTreffer = 0
foreach ($p in $werPfade) {
    if (-not (Test-Path $p)) { continue }
    $berichte = Get-ChildItem $p -Recurse -Filter 'Report.wer' -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 20
    foreach ($b in $berichte) {
        $inhalt = Get-Content $b.FullName -ErrorAction SilentlyContinue
        if ($inhalt -match 'fexobooth') {
            $werTreffer++
            Zeile ''
            Zeile ("--- " + $b.LastWriteTime + " | " + $b.FullName + " ---")
            foreach ($z in ($inhalt | Select-Object -First 45)) { if ($z.Trim()) { Zeile ("    " + $z.Trim()) } }
        }
    }
}
if ($werTreffer -eq 0) { Zeile 'Keine WER-Berichte zu fexobooth gefunden (evtl. Adminrechte noetig).' }

# ---------------------------------------------------------------
# 5. Speicherabbilder + logs-Ordner
# ---------------------------------------------------------------
Titel 'SPEICHERABBILDER UND LOG-DATEIEN'
$dumpDir = 'C:\FexoBooth\logs\dumps'
if (Test-Path $dumpDir) {
    $dumps = Get-ChildItem $dumpDir -Filter '*.dmp' -ErrorAction SilentlyContinue
    if ($dumps) {
        foreach ($d in $dumps) { Zeile ("  DUMP: " + $d.Name + "  (" + [math]::Round($d.Length/1MB,1) + " MB, " + $d.LastWriteTime + ")") }
        Zeile '  -> Diese .dmp-Dateien bitte MITSCHICKEN, sie zeigen die schuldige DLL.'
    } else { Zeile '  Noch keine Speicherabbilder vorhanden.' }
} else { Zeile '  Ordner fuer Speicherabbilder existiert noch nicht.' }

Zeile ''
Zeile 'Inhalt von C:\FexoBooth\logs:'
try {
    Get-ChildItem $logDir -File | Sort-Object LastWriteTime -Descending |
        ForEach-Object { Zeile ("  " + $_.LastWriteTime.ToString('dd.MM. HH:mm') + "  " + $_.Length.ToString().PadLeft(9) + "  " + $_.Name) }
} catch { Zeile '  (nicht lesbar)' }

# absturz.log der App anhaengen (dort steht der Python-Stack)
$appAbsturz = Join-Path $logDir 'absturz.log'
if (Test-Path $appAbsturz) {
    Titel 'ABSTURZ.LOG DER APP (letzte 80 Zeilen)'
    foreach ($z in (Get-Content $appAbsturz -Tail 80)) { Zeile $z }
}

# ---------------------------------------------------------------
# 6. Speicherabbild fuer den NAECHSTEN Absturz aktivieren
# ---------------------------------------------------------------
Titel 'SPEICHERABBILD FUER DEN NAECHSTEN ABSTURZ'
if ($istAdmin) {
    try {
        $k = 'HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\fexobooth.exe'
        if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
        New-ItemProperty -Path $k -Name 'DumpFolder' -Value 'C:\FexoBooth\logs\dumps' -PropertyType ExpandString -Force | Out-Null
        New-ItemProperty -Path $k -Name 'DumpCount'  -Value 5 -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $k -Name 'DumpType'   -Value 2 -PropertyType DWord -Force | Out-Null
        Zeile 'AKTIVIERT: Der naechste Absturz legt ein Speicherabbild in C:\FexoBooth\logs\dumps ab.'
        Write-Host '   [OK] Speicherabbild fuer den naechsten Absturz aktiviert.' -ForegroundColor Green
    } catch {
        Zeile ('Konnte nicht aktiviert werden: ' + $_.Exception.Message)
    }
} else {
    Zeile 'UEBERSPRUNGEN - dafuer diese Datei bitte einmal per Rechtsklick'
    Zeile '"Als Administrator ausfuehren" starten.'
    Write-Host '   [i] Fuer Speicherabbilder: Rechtsklick -> Als Administrator ausfuehren' -ForegroundColor Yellow
}

# ---------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------
try {
    $L -join "`r`n" | Out-File -FilePath $out -Encoding utf8 -Force
    Write-Host ''
    Write-Host '   [OK] Fertig!' -ForegroundColor Green
    Write-Host ('   Datei: ' + $out) -ForegroundColor White
    Write-Host ''
    if ($gefunden -gt 0) {
        Write-Host ('   ' + $gefunden + ' Absturzmeldung(en) zu fexobooth gefunden.') -ForegroundColor Yellow
    } else {
        Write-Host '   Keine Absturzmeldung zu fexobooth gefunden.' -ForegroundColor Yellow
    }
    Write-Host ''
    Write-Host '   NAECHSTER SCHRITT: Ordner C:\FexoBooth\logs komplett' -ForegroundColor Cyan
    Write-Host '   auf den USB-Stick kopieren.' -ForegroundColor Cyan
} catch {
    Write-Host ('   FEHLER beim Schreiben: ' + $_.Exception.Message) -ForegroundColor Red
}
