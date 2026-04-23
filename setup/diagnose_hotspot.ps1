# ============================================
# FEXOBOX HOTSPOT DIAGNOSE + AUTO-FIX
# ============================================
# Schreibt ein detailliertes Log auf den Desktop
# mit allen Infos die man braucht um zu verstehen
# warum der Hotspot nicht startet.
#
# Versucht gleichzeitig die gaengigen Fixes.
# ============================================

param(
    [string]$SSID = "fexobox-gallery",
    [string]$Password = "fotobox123"
)

# ─────────────────────────────────────────────
# Log-Datei auf dem Desktop
# ─────────────────────────────────────────────
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$desktop = [Environment]::GetFolderPath("Desktop")
$logFile = Join-Path $desktop "hotspot_diagnose_$timestamp.log"

# Falls ein USB-Stick mit Label FEXODATEN steckt: zusaetzlich dorthin schreiben
$usbLogFile = $null
try {
    $usbDrive = Get-Volume -ErrorAction SilentlyContinue | Where-Object { $_.FileSystemLabel -eq "FEXODATEN" } | Select-Object -First 1
    if ($usbDrive -and $usbDrive.DriveLetter) {
        $usbLogDir = "$($usbDrive.DriveLetter):\hotspot-diagnose"
        New-Item -ItemType Directory -Path $usbLogDir -Force -ErrorAction SilentlyContinue | Out-Null
        $usbLogFile = Join-Path $usbLogDir "hotspot_diagnose_$timestamp.log"
    }
} catch {}

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $line = $Message
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    if ($usbLogFile) {
        Add-Content -Path $usbLogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    }
}

function Write-Section {
    param([string]$Title)
    Write-Log ""
    Write-Log ("=" * 60) "Cyan"
    Write-Log "  $Title" "Cyan"
    Write-Log ("=" * 60) "Cyan"
}

# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────
Write-Log ""
Write-Log "FEXOBOX HOTSPOT DIAGNOSE" "Yellow"
Write-Log "Zeit: $(Get-Date)"
Write-Log "Log: $logFile"
if ($usbLogFile) { Write-Log "Zusaetzlich auf USB: $usbLogFile" }

# ─────────────────────────────────────────────
# SYSTEM-INFO
# ─────────────────────────────────────────────
Write-Section "SYSTEM-INFO"
try {
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
    $bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
    Write-Log "Computer:     $($cs.Manufacturer) $($cs.Model)"
    Write-Log "Seriennummer: $($bios.SerialNumber)"
    Write-Log "Windows:      $($os.Caption) $($os.Version)"
    Write-Log "Hostname:     $env:COMPUTERNAME"
} catch {
    Write-Log "Fehler beim Lesen der System-Info: $_" "Red"
}

# ─────────────────────────────────────────────
# NETZWERK-ADAPTER
# ─────────────────────────────────────────────
Write-Section "NETZWERK-ADAPTER (alle)"
try {
    $adapters = Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue
    foreach ($a in $adapters) {
        Write-Log ("  [{0,-10}] {1,-40} | Type: {2,-20} | {3}" -f $a.Status, $a.Name, $a.InterfaceDescription, $a.MediaType)
    }
} catch {
    Write-Log "Fehler: $_" "Red"
}

# ─────────────────────────────────────────────
# WLAN-INTERFACES
# ─────────────────────────────────────────────
Write-Section "WLAN-INTERFACES (netsh wlan show interfaces)"
$wlanInterfaces = & netsh wlan show interfaces 2>&1
Write-Log ($wlanInterfaces -join "`r`n")

# ─────────────────────────────────────────────
# HOSTED NETWORK SUPPORT (entscheidend!)
# ─────────────────────────────────────────────
Write-Section "WLAN-TREIBER FAEHIGKEITEN (netsh wlan show drivers)"
$wlanDrivers = & netsh wlan show drivers 2>&1
Write-Log ($wlanDrivers -join "`r`n")

$hostedNetworkSupported = $false
if ($wlanDrivers -match "Hosted network supported\s*:\s*Yes" -or $wlanDrivers -match "Gehostetes Netzwerk.*:\s*Ja") {
    $hostedNetworkSupported = $true
    Write-Log ""
    Write-Log ">>> Hosted Network: UNTERSTUETZT" "Green"
} else {
    Write-Log ""
    Write-Log ">>> Hosted Network: NICHT UNTERSTUETZT" "Yellow"
    Write-Log "    (Das ist das Haupt-Indiz wenn der Offline-Hotspot nicht startet!)" "Yellow"
}

# ─────────────────────────────────────────────
# WICHTIGE DIENSTE
# ─────────────────────────────────────────────
Write-Section "WINDOWS-DIENSTE (fuer Hotspot relevant)"
$services = @(
    @{Name="WlanSvc";        Desc="WLAN-Dienst"},
    @{Name="SharedAccess";   Desc="Internet Connection Sharing (ICS)"},
    @{Name="icssvc";         Desc="Windows Mobile Hotspot-Dienst"},
    @{Name="NlaSvc";         Desc="Netzwerklistendienst"},
    @{Name="netprofm";       Desc="Netzwerklisten-Dienst"}
)
foreach ($s in $services) {
    $svc = Get-Service -Name $s.Name -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Log ("  {0,-15} ({1,-40}) | Status: {2,-8} | StartType: {3}" -f $s.Name, $s.Desc, $svc.Status, $svc.StartType)
    } else {
        Write-Log ("  {0,-15} ({1}) | NICHT VORHANDEN" -f $s.Name, $s.Desc) "Yellow"
    }
}

# ─────────────────────────────────────────────
# AKTUELLER HOSTEDNETWORK-STATUS
# ─────────────────────────────────────────────
Write-Section "HOSTED NETWORK STATUS (netsh wlan show hostednetwork)"
$hnStatus = & netsh wlan show hostednetwork 2>&1
Write-Log ($hnStatus -join "`r`n")

# ─────────────────────────────────────────────
# CONNECTION PROFILES (fuer Tethering API)
# ─────────────────────────────────────────────
Write-Section "CONNECTION PROFILES (fuer Tethering API)"
try {
    [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
    $profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
    if ($profiles) {
        foreach ($p in $profiles) {
            Write-Log ("  Profil: {0,-40} | Authentication: {1}" -f $p.ProfileName, $p.GetNetworkConnectivityLevel())
        }
    } else {
        Write-Log "  KEINE Connection Profiles gefunden" "Yellow"
    }

    $internetProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    if ($internetProfile) {
        Write-Log "  >>> Internet-Profil: $($internetProfile.ProfileName)" "Green"
    } else {
        Write-Log "  >>> KEIN Internet-Profil (das ist der Grund warum die Windows-UI den Hotspot blockiert)" "Yellow"
    }
} catch {
    Write-Log "Fehler beim Laden der Connection Profiles: $_" "Red"
}

# ─────────────────────────────────────────────
# POWER-MANAGEMENT des WLAN-Adapters
# ─────────────────────────────────────────────
Write-Section "POWER-MANAGEMENT (WLAN-Adapter)"
try {
    $wlanAdapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.MediaType -match "802.11|Native 802" -or $_.InterfaceDescription -match "Wireless|WiFi|WLAN" }
    foreach ($a in $wlanAdapters) {
        $pm = Get-NetAdapterPowerManagement -Name $a.Name -ErrorAction SilentlyContinue
        if ($pm) {
            Write-Log "  Adapter: $($a.Name)"
            Write-Log "    Allow Computer to turn off: $($pm.AllowComputerToTurnOffDevice)"
            Write-Log "    DeviceSleepOnDisconnect:    $($pm.DeviceSleepOnDisconnect)"
        }
    }
} catch {
    Write-Log "Fehler beim Lesen der Power-Settings: $_" "Red"
}

# ==============================================================
# AUTO-FIX SEKTION
# ==============================================================
Write-Section "AUTO-FIX 1: WLAN-Dienste sicherstellen"
foreach ($svcName in @("WlanSvc", "SharedAccess", "icssvc")) {
    try {
        Set-Service -Name $svcName -StartupType Automatic -ErrorAction SilentlyContinue
        $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne "Running") {
            Start-Service -Name $svcName -ErrorAction SilentlyContinue
            Write-Log "  $svcName gestartet"
        } elseif ($svc) {
            Write-Log "  $svcName laeuft bereits"
        }
    } catch {
        Write-Log "  $svcName konnte nicht gestartet werden: $_" "Yellow"
    }
}

Write-Section "AUTO-FIX 2: Power-Management fuer WLAN-Adapter deaktivieren"
try {
    $wlanAdapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.MediaType -match "802.11|Native 802" -or $_.InterfaceDescription -match "Wireless|WiFi|WLAN" }
    foreach ($a in $wlanAdapters) {
        try {
            Set-NetAdapterPowerManagement -Name $a.Name -AllowComputerToTurnOffDevice Disabled -ErrorAction SilentlyContinue
            Write-Log "  $($a.Name): AllowComputerToTurnOffDevice = Disabled"
        } catch {
            Write-Log "  $($a.Name): konnte nicht geaendert werden ($_)" "Yellow"
        }
    }
} catch {
    Write-Log "Fehler: $_" "Red"
}

Write-Section "AUTO-FIX 3: WLAN-Adapter re-enable"
try {
    $wlanAdapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.MediaType -match "802.11|Native 802" -or $_.InterfaceDescription -match "Wireless|WiFi|WLAN" }
    foreach ($a in $wlanAdapters) {
        if ($a.Status -ne "Up") {
            Write-Log "  $($a.Name) ist $($a.Status) - versuche zu aktivieren..."
            Enable-NetAdapter -Name $a.Name -Confirm:$false -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        } else {
            Write-Log "  $($a.Name) bereits Up"
        }
    }
} catch {
    Write-Log "Fehler: $_" "Red"
}

Write-Section "AUTO-FIX 4: Hosted Network neu konfigurieren und starten"
if ($hostedNetworkSupported) {
    Write-Log "  Setze SSID=$SSID / Key=$Password"
    $setResult = & netsh wlan set hostednetwork mode=allow ssid="$SSID" key="$Password" 2>&1
    Write-Log "  $setResult"

    Write-Log "  Starte Hosted Network..."
    $startResult = & netsh wlan start hostednetwork 2>&1
    Write-Log "  $startResult"
} else {
    Write-Log "  Hosted Network wird nicht unterstuetzt - ueberspringe"
    Write-Log "  Versuche stattdessen Tethering API..."

    try {
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
        [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

        $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

        function Await($WinRtTask, $ResultType) {
            $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
            $netTask = $asTask.Invoke($null, @($WinRtTask))
            $netTask.Wait(-1) | Out-Null
            $netTask.Result
        }

        $tm = $null
        $profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
        foreach ($p in $profiles) {
            try {
                $candidate = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($p)
                if ($candidate) { $tm = $candidate; Write-Log "  Tethering Manager aus Profil: $($p.ProfileName)"; break }
            } catch { continue }
        }

        if ($tm) {
            if ($tm.TetheringOperationalState -eq "On") {
                Write-Log "  Tethering laeuft bereits" "Green"
            } else {
                $result = Await ($tm.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
                Write-Log "  Tethering Start-Result: $($result.Status)"
            }
        } else {
            Write-Log "  Konnte keinen Tethering Manager erstellen" "Red"
        }
    } catch {
        Write-Log "  Tethering API Fehler: $_" "Red"
    }
}

# ─────────────────────────────────────────────
# ERGEBNIS
# ─────────────────────────────────────────────
Write-Section "ERGEBNIS (netsh wlan show hostednetwork NACH Fix)"
Start-Sleep -Seconds 2
$finalStatus = & netsh wlan show hostednetwork 2>&1
Write-Log ($finalStatus -join "`r`n")

# Erkenne ob's jetzt laeuft
$success = $false
if ($finalStatus -match "Status\s*:\s*(Started|Gestartet)") {
    $success = $true
    Write-Log ""
    Write-Log ">>> HOTSPOT LAEUFT via hostednetwork" "Green"
}

# Zusaetzlich Tethering-Status checken
try {
    [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
    [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null
    $profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
    foreach ($p in $profiles) {
        try {
            $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($p)
            if ($tm -and $tm.TetheringOperationalState -eq "On") {
                $success = $true
                Write-Log ">>> HOTSPOT LAEUFT via Tethering API" "Green"
                break
            }
        } catch { continue }
    }
} catch {}

Write-Log ""
Write-Log ("=" * 60) "Cyan"
if ($success) {
    Write-Log "  ERGEBNIS: HOTSPOT LAEUFT" "Green"
} else {
    Write-Log "  ERGEBNIS: HOTSPOT LAEUFT NICHT" "Red"
    Write-Log ""
    Write-Log "  NAECHSTE SCHRITTE:" "Yellow"
    if (-not $hostedNetworkSupported) {
        Write-Log "  1. Hosted Network wird nicht unterstuetzt. Moeglich:"
        Write-Log "     - WLAN-Adapter im Stromsparmodus -> Tablet neu starten"
        Write-Log "     - WLAN-Treiber wurde aktualisiert -> repair_wlan_driver.bat probieren"
        Write-Log "     - Treiber deinstalliert und ohne Netz neu installiert"
    } else {
        Write-Log "  1. Hosted Network wird unterstuetzt aber startet nicht. Moeglich:"
        Write-Log "     - icssvc/SharedAccess Dienst blockiert"
        Write-Log "     - Eventlog pruefen: Get-EventLog -LogName System -Newest 50"
        Write-Log "     - Antivirus blockiert netsh"
    }
    Write-Log ""
    Write-Log "  Log an Christian schicken: $logFile"
}
Write-Log ("=" * 60) "Cyan"

# Exit-Code: 0 = Erfolg, 1 = Hotspot laeuft nicht
if ($success) { exit 0 } else { exit 1 }
