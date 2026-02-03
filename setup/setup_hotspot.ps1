# ============================================
# FEXOBOX HOTSPOT SETUP (PowerShell)
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
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

function AwaitAction($WinRtAction) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and !$_.IsGenericMethod })[0]
    $netTask = $asTask.Invoke($null, @($WinRtAction))
    $netTask.Wait(-1) | Out-Null
}

Write-Host "[2/5] Hole Tethering Manager..." -ForegroundColor Cyan

# NetworkOperatorTetheringManager holen
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

$connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
$tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)

Write-Host "[3/5] Konfiguriere Hotspot..." -ForegroundColor Cyan
Write-Host "   SSID: $SSID"
Write-Host "   Passwort: $Password"

# Konfiguration holen und setzen
$config = $tetheringManager.GetCurrentAccessPointConfiguration()
$config.Ssid = $SSID
$config.Passphrase = $Password

# Async konfigurieren
$configResult = Await ($tetheringManager.ConfigureAccessPointAsync($config)) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])

if ($configResult.Status -eq "Success") {
    Write-Host "   Konfiguration erfolgreich!" -ForegroundColor Green
} else {
    Write-Host "   WARNUNG: $($configResult.Status)" -ForegroundColor Yellow
}

Write-Host "[4/5] Erstelle Auto-Start Task..." -ForegroundColor Cyan

# PowerShell-Script fuer Auto-Start erstellen
$startScript = @'
# Hotspot starten
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null
$connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
$tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$result = Await ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
Write-Host "Hotspot Status: $($result.Status)"
'@

$scriptPath = "$env:USERPROFILE\start_fexobox_hotspot.ps1"
$startScript | Out-File -FilePath $scriptPath -Encoding UTF8
Write-Host "   Script gespeichert: $scriptPath"

# Scheduled Task erstellen
$taskName = "FexoboxHotspot"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# Alten Task loeschen falls vorhanden
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Neuen Task erstellen
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Write-Host "   Scheduled Task erstellt: $taskName" -ForegroundColor Green

Write-Host "[5/5] Starte Hotspot jetzt..." -ForegroundColor Cyan

$startResult = Await ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])

if ($startResult.Status -eq "Success") {
    Write-Host "   Hotspot gestartet!" -ForegroundColor Green
} else {
    Write-Host "   Status: $($startResult.Status)" -ForegroundColor Yellow
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
Write-Host "Der Hotspot startet automatisch bei jedem Login."
Write-Host ""
Write-Host "TESTEN:" -ForegroundColor Yellow
Write-Host "1. Mit Handy mit '$SSID' verbinden"
Write-Host "2. Browser oeffnen: http://192.168.137.1:8080"
Write-Host ""
pause
