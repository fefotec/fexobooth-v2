# ============================================
# FEXOBOX HOTSPOT SETUP (PowerShell)
# ============================================
# FUNKTIONIERT OFFLINE mit Loopback-Adapter!
# Kompatibel mit Geraeten OHNE "Hosted Network"
# (z.B. Lenovo Miix 310)
# ============================================
# Als Administrator ausfuehren:
# Right-click > Run with PowerShell (as Admin)
# ============================================

param(
    [string]$SSID = "fexobox-gallery",
    [string]$Password = "fotobox123"
)

Write-Host ""
Write-Host "========================================"
Write-Host "   FEXOBOX HOTSPOT SETUP"
Write-Host "   (Loopback-Methode fuer Offline)"
Write-Host "========================================"
Write-Host ""

# Admin-Check
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "FEHLER: Bitte als Administrator ausfuehren!" -ForegroundColor Red
    Write-Host "Rechtsklick > 'Mit PowerShell als Administrator ausfuehren'"
    pause
    exit 1
}

Write-Host "[1/5] Lade Windows Runtime APIs..." -ForegroundColor Cyan

# Windows Runtime Types laden
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    Write-Host "   Windows Runtime geladen" -ForegroundColor Green
} catch {
    Write-Host "   FEHLER: Windows Runtime nicht verfuegbar: $_" -ForegroundColor Red
    pause
    exit 1
}

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

Write-Host "[2/5] Pruefe/Erstelle Loopback-Adapter..." -ForegroundColor Cyan

# Pruefen ob Microsoft Loopback Adapter existiert
$loopbackAdapter = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match "Microsoft KM-TEST Loopback Adapter|Loopback" }

if (-not $loopbackAdapter) {
    Write-Host "   Erstelle Loopback-Adapter..." -ForegroundColor Yellow

    # Loopback Adapter installieren (erfordert devcon oder manuell)
    # Alternative: Wir versuchen es ohne Loopback mit dem ersten verfuegbaren Profil
    Write-Host "   Kein Loopback-Adapter gefunden, versuche alternative Methode..." -ForegroundColor Yellow
} else {
    Write-Host "   Loopback-Adapter gefunden: $($loopbackAdapter.Name)" -ForegroundColor Green
}

Write-Host "[3/5] Hole Tethering Manager..." -ForegroundColor Cyan

# NetworkOperatorTetheringManager holen
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

# Versuche verschiedene Connection Profiles
$tetheringManager = $null
$methodUsed = ""

# Methode 1: Loopback-Profil (funktioniert offline!)
try {
    $profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
    $loopbackProfile = $profiles | Where-Object { $_.ProfileName -match "loopback|Loopback" }

    if ($loopbackProfile) {
        $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($loopbackProfile)
        $methodUsed = "Loopback-Profil"
        Write-Host "   Verwende Loopback-Profil" -ForegroundColor Green
    }
} catch {
    Write-Host "   Loopback-Profil nicht verfuegbar" -ForegroundColor Gray
}

# Methode 2: Erstes verfuegbares Profil
if (-not $tetheringManager) {
    try {
        $profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
        foreach ($profile in $profiles) {
            try {
                $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
                if ($tetheringManager) {
                    $methodUsed = "Profil: $($profile.ProfileName)"
                    Write-Host "   Verwende Profil: $($profile.ProfileName)" -ForegroundColor Green
                    break
                }
            } catch {
                continue
            }
        }
    } catch {
        Write-Host "   Kein Verbindungsprofil gefunden" -ForegroundColor Gray
    }
}

# Methode 3: Internet Connection Profile (braucht Internet)
if (-not $tetheringManager) {
    try {
        $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
        if ($connectionProfile) {
            $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
            $methodUsed = "Internet-Profil"
            Write-Host "   Verwende Internet-Profil" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "   Kein Internet-Profil verfuegbar" -ForegroundColor Gray
    }
}

# Methode 4: netsh hostednetwork als Fallback
if (-not $tetheringManager) {
    Write-Host ""
    Write-Host "   WiFi Direct API nicht verfuegbar!" -ForegroundColor Yellow
    Write-Host "   Versuche netsh hostednetwork als Fallback..." -ForegroundColor Yellow

    # Pruefen ob Hosted Network unterstuetzt wird
    $driverInfo = netsh wlan show drivers 2>&1
    $hostedSupported = ($driverInfo | Select-String "Hosted network supported\s*:\s*Yes" -Quiet) -or `
                       ($driverInfo | Select-String "Gehostetes Netzwerk unterst.*:\s*Ja" -Quiet)

    if ($hostedSupported) {
        Write-Host "   Hosted Network wird unterstuetzt, konfiguriere..." -ForegroundColor Green
        netsh wlan set hostednetwork mode=allow ssid="$SSID" key="$Password" | Out-Null
        $startResult = netsh wlan start hostednetwork 2>&1

        if ($startResult -match "gestartet|started") {
            Write-Host ""
            Write-Host "======================================== " -ForegroundColor Green
            Write-Host "   HOTSPOT GESTARTET (netsh)!" -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
            Write-Host ""
            Write-Host "Hotspot-Daten:" -ForegroundColor Cyan
            Write-Host "   SSID:     $SSID"
            Write-Host "   Passwort: $Password"
            Write-Host "   IP:       192.168.137.1"
            Write-Host ""

            # Auto-Start einrichten
            $startScript = @"

# Fexobox Hotspot Auto-Start (netsh)
Start-Sleep -Seconds 5
netsh wlan start hostednetwork
"@
            $scriptPath = "$env:USERPROFILE\start_fexobox_hotspot.ps1"
            $startScript | Out-File -FilePath $scriptPath -Encoding UTF8

            $taskName = "FexoboxHotspot"
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
            $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
            $trigger = New-ScheduledTaskTrigger -AtLogOn
            $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
            $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
            Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
            Write-Host "Auto-Start eingerichtet!" -ForegroundColor Green
            pause
            exit 0
        }
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "   AUTOMATISCHES SETUP FEHLGESCHLAGEN" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Bitte den Hotspot MANUELL einrichten:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Windows-Einstellungen oeffnen (Win + I)" -ForegroundColor Cyan
    Write-Host "2. Netzwerk und Internet > Mobiler Hotspot" -ForegroundColor Cyan
    Write-Host "3. 'Mobiler Hotspot' EINSCHALTEN" -ForegroundColor Cyan
    Write-Host "4. Auf 'Bearbeiten' klicken und einstellen:" -ForegroundColor Cyan
    Write-Host "   - Netzwerkname: $SSID" -ForegroundColor White
    Write-Host "   - Kennwort: $Password" -ForegroundColor White
    Write-Host "5. 'Energiesparmodus' AUSSCHALTEN" -ForegroundColor Cyan
    Write-Host "   (damit Hotspot aktiv bleibt)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Der manuell eingerichtete Hotspot funktioniert" -ForegroundColor Green
    Write-Host "auch OHNE Internetverbindung!" -ForegroundColor Green
    Write-Host ""
    pause
    exit 1
}

Write-Host "[4/5] Konfiguriere Hotspot ($methodUsed)..." -ForegroundColor Cyan
Write-Host "   SSID: $SSID"
Write-Host "   Passwort: $Password"

# Konfiguration holen und setzen
try {
    $config = $tetheringManager.GetCurrentAccessPointConfiguration()
    $config.Ssid = $SSID
    $config.Passphrase = $Password

    # Async konfigurieren
    $configResult = Await ($tetheringManager.ConfigureAccessPointAsync($config)) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])

    if ($configResult.Status -eq "Success") {
        Write-Host "   Konfiguration erfolgreich!" -ForegroundColor Green
    } else {
        Write-Host "   Konfiguration: $($configResult.Status)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   WARNUNG: Konfiguration fehlgeschlagen: $_" -ForegroundColor Yellow
    Write-Host "   Versuche trotzdem zu starten..." -ForegroundColor Gray
}

Write-Host "[5/5] Starte Hotspot..." -ForegroundColor Cyan

try {
    $startResult = Await ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])

    if ($startResult.Status -eq "Success") {
        Write-Host "   Hotspot gestartet!" -ForegroundColor Green

        # Auto-Start Script erstellen
        $startScript = @"
# Fexobox Hotspot Auto-Start
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

Start-Sleep -Seconds 5

`$profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
foreach (`$profile in `$profiles) {
    try {
        `$tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile(`$profile)
        if (`$tm) {
            `$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { `$_.Name -eq 'AsTask' -and `$_.GetParameters().Count -eq 1 -and `$_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation``1' })[0]
            `$asTask = `$asTaskGeneric.MakeGenericMethod([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
            `$netTask = `$asTask.Invoke(`$null, @(`$tm.StartTetheringAsync()))
            `$netTask.Wait(-1) | Out-Null
            break
        }
    } catch { continue }
}
"@

        $scriptPath = "$env:USERPROFILE\start_fexobox_hotspot.ps1"
        $startScript | Out-File -FilePath $scriptPath -Encoding UTF8
        Write-Host "   Auto-Start Script: $scriptPath" -ForegroundColor Gray

        # Scheduled Task erstellen
        $taskName = "FexoboxHotspot"
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
        Write-Host "   Scheduled Task erstellt: $taskName" -ForegroundColor Green

    } else {
        Write-Host "   Start-Status: $($startResult.Status)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   Start fehlgeschlagen: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================"
Write-Host "   SETUP ABGESCHLOSSEN!"
Write-Host "========================================"
Write-Host ""
Write-Host "Hotspot-Daten:" -ForegroundColor Cyan
Write-Host "   SSID:     $SSID"
Write-Host "   Passwort: $Password"
Write-Host "   IP:       192.168.137.1"
Write-Host ""
Write-Host "Methode: $methodUsed" -ForegroundColor Gray
Write-Host ""
Write-Host "TESTEN:" -ForegroundColor Yellow
Write-Host "1. Mit Handy mit '$SSID' verbinden"
Write-Host "2. Browser oeffnen: http://192.168.137.1:8080"
Write-Host ""

# Energiesparmodus-Hinweis
Write-Host "WICHTIG: Energiesparmodus deaktivieren!" -ForegroundColor Yellow
Write-Host "Windows-Einstellungen > Netzwerk > Mobiler Hotspot" -ForegroundColor Gray
Write-Host "'Wenn keine Geraete verbunden sind, Hotspot ausschalten' -> AUS" -ForegroundColor Gray
Write-Host ""

pause
