"""Windows Mobile Hotspot Steuerung

Startet/stoppt den Windows Mobile Hotspot programmatisch.
Wird von der Fexobooth-Software genutzt wenn gallery_enabled=true.
"""

import subprocess
import sys
from src.utils.logging import get_logger

logger = get_logger(__name__)

# PowerShell-Script zum Starten des Hotspots
_START_HOTSPOT_PS = '''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

$connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($connectionProfile -eq $null) {
    Write-Host "NO_INTERNET"
    exit 1
}

$tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)

# Status prüfen
$state = $tetheringManager.TetheringOperationalState
if ($state -eq "On") {
    Write-Host "ALREADY_ON"
    exit 0
}

# Starten
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

try {
    $result = Await ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    Write-Host $result.Status
} catch {
    Write-Host "ERROR: $_"
    exit 1
}
'''

# PowerShell-Script zum Stoppen des Hotspots
_STOP_HOTSPOT_PS = '''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

$connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($connectionProfile -eq $null) {
    Write-Host "NO_INTERNET"
    exit 0
}

$tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)

# Status prüfen
$state = $tetheringManager.TetheringOperationalState
if ($state -eq "Off") {
    Write-Host "ALREADY_OFF"
    exit 0
}

# Stoppen
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

try {
    $result = Await ($tetheringManager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    Write-Host $result.Status
} catch {
    Write-Host "ERROR: $_"
    exit 1
}
'''

# PowerShell-Script zum Prüfen des Hotspot-Status
_CHECK_HOTSPOT_PS = '''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

$connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($connectionProfile -eq $null) {
    Write-Host "NO_INTERNET"
    exit 0
}

$tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
Write-Host $tetheringManager.TetheringOperationalState
'''


def _run_powershell(script: str) -> tuple[bool, str]:
    """Führt PowerShell-Script aus und gibt (success, output) zurück"""
    if sys.platform != "win32":
        return False, "NOT_WINDOWS"

    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW  # Kein Fenster anzeigen
        )
        output = result.stdout.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def start_hotspot() -> bool:
    """Startet den Windows Mobile Hotspot

    Returns:
        True wenn erfolgreich oder bereits aktiv
    """
    logger.info("🌐 Starte Windows Mobile Hotspot...")

    success, output = _run_powershell(_START_HOTSPOT_PS)

    if output == "ALREADY_ON":
        logger.info("✅ Hotspot war bereits aktiv")
        return True
    elif output == "Success" or success:
        logger.info("✅ Hotspot erfolgreich gestartet")
        return True
    elif output == "NO_INTERNET":
        logger.warning("⚠️ Kein Internet - Hotspot kann nicht gestartet werden")
        return False
    else:
        logger.error(f"❌ Hotspot-Start fehlgeschlagen: {output}")
        return False


def stop_hotspot() -> bool:
    """Stoppt den Windows Mobile Hotspot

    Returns:
        True wenn erfolgreich oder bereits aus
    """
    logger.info("🌐 Stoppe Windows Mobile Hotspot...")

    success, output = _run_powershell(_STOP_HOTSPOT_PS)

    if output == "ALREADY_OFF":
        logger.info("✅ Hotspot war bereits aus")
        return True
    elif output == "Success" or success:
        logger.info("✅ Hotspot erfolgreich gestoppt")
        return True
    else:
        logger.warning(f"⚠️ Hotspot-Stop: {output}")
        return False


def is_hotspot_active() -> bool:
    """Prüft ob der Hotspot aktiv ist"""
    success, output = _run_powershell(_CHECK_HOTSPOT_PS)
    return output == "On"


def ensure_hotspot_state(should_be_active: bool) -> bool:
    """Stellt sicher dass der Hotspot im gewünschten Zustand ist

    Args:
        should_be_active: True = Hotspot soll an sein, False = soll aus sein

    Returns:
        True wenn Zustand erreicht wurde
    """
    if should_be_active:
        return start_hotspot()
    else:
        return stop_hotspot()
