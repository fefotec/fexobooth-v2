"""Windows Hotspot Steuerung - Offline-fähig

Startet/stoppt einen WLAN-Hotspot für die Foto-Galerie.
Funktioniert auch OHNE Internetverbindung!

Methoden (in Prioritätsreihenfolge):
1. Windows Tethering API mit beliebigem Connection Profile
2. netsh wlan hostednetwork (Offline-Fallback)
"""

import subprocess
import sys
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Welche Methode beim letzten Start verwendet wurde
_active_method: str = ""  # "tethering" oder "hostednetwork"

# Standard SSID/Passwort (werden von start_hotspot überschrieben)
_DEFAULT_SSID = "fexobox-gallery"
_DEFAULT_PASSWORD = "fotobox123"

# ─────────────────────────────────────────────
# PowerShell: Tethering API (mit allen Profilen, nicht nur Internet!)
# ─────────────────────────────────────────────

_START_TETHERING_PS = '''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}

$tetheringManager = $null

# Methode 1: Alle Connection Profiles durchprobieren (funktioniert auch ohne Internet!)
$profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
foreach ($profile in $profiles) {{
    try {{
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
        if ($tm) {{
            $tetheringManager = $tm
            break
        }}
    }} catch {{ continue }}
}}

# Methode 2: Internet-Profil als letzter Versuch
if (-not $tetheringManager) {{
    try {{
        $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
        if ($connectionProfile) {{
            $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
        }}
    }} catch {{}}
}}

if (-not $tetheringManager) {{
    Write-Host "NO_PROFILE"
    exit 1
}}

# Status pruefen
$state = $tetheringManager.TetheringOperationalState
if ($state -eq "On") {{
    Write-Host "ALREADY_ON"
    exit 0
}}

# Starten
try {{
    $result = Await ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    Write-Host $result.Status
}} catch {{
    Write-Host "ERROR: $_"
    exit 1
}}
'''

_STOP_TETHERING_PS = '''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}

$tetheringManager = $null

# Alle Connection Profiles durchprobieren
$profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
foreach ($profile in $profiles) {{
    try {{
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
        if ($tm -and $tm.TetheringOperationalState -eq "On") {{
            $tetheringManager = $tm
            break
        }}
    }} catch {{ continue }}
}}

if (-not $tetheringManager) {{
    # Fallback: Internet-Profil
    try {{
        $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
        if ($connectionProfile) {{
            $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
        }}
    }} catch {{}}
}}

if (-not $tetheringManager) {{
    Write-Host "NOT_RUNNING"
    exit 0
}}

$state = $tetheringManager.TetheringOperationalState
if ($state -eq "Off") {{
    Write-Host "ALREADY_OFF"
    exit 0
}}

try {{
    $result = Await ($tetheringManager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    Write-Host $result.Status
}} catch {{
    Write-Host "ERROR: $_"
    exit 1
}}
'''

_CHECK_TETHERING_PS = '''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

# Alle Connection Profiles durchprobieren
$profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
foreach ($profile in $profiles) {
    try {
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
        if ($tm -and $tm.TetheringOperationalState -eq "On") {
            Write-Host "On"
            exit 0
        }
    } catch { continue }
}

# Fallback: Internet-Profil
try {
    $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    if ($connectionProfile) {
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
        Write-Host $tm.TetheringOperationalState
        exit 0
    }
} catch {}

Write-Host "Off"
'''


def _run_powershell(script: str) -> tuple[bool, str]:
    """Fuehrt PowerShell-Script aus und gibt (success, output) zurueck"""
    if sys.platform != "win32":
        return False, "NOT_WINDOWS"

    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        # Nicht text=True verwenden (cp1252 Encoding-Fehler auf dt. Windows)
        output = result.stdout.decode("utf-8", errors="replace").strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def _run_netsh(args: list[str]) -> tuple[bool, str]:
    """Fuehrt netsh-Befehl aus"""
    if sys.platform != "win32":
        return False, "NOT_WINDOWS"

    try:
        result = subprocess.run(
            ["netsh"] + args,
            capture_output=True,
            timeout=15,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = result.stdout.strip()
        return result.returncode == 0, output
    except Exception as e:
        return False, f"ERROR: {e}"


def _is_hostednetwork_supported() -> bool:
    """Prueft ob netsh wlan hostednetwork unterstuetzt wird"""
    success, output = _run_netsh(["wlan", "show", "drivers"])
    if not success:
        return False
    # Englisch und Deutsch pruefen
    return ("Hosted network supported" in output and "Yes" in output) or \
           ("Gehostetes Netzwerk" in output and "Ja" in output)


# ─────────────────────────────────────────────
# Oeffentliche API
# ─────────────────────────────────────────────

def start_hotspot(ssid: str = "", password: str = "") -> bool:
    """Startet den WLAN-Hotspot (funktioniert auch ohne Internet!)

    Versucht in Reihenfolge:
    1. Windows Tethering API (alle Connection Profiles)
    2. netsh wlan hostednetwork (Offline-Fallback)

    Args:
        ssid: WLAN-Name (optional, fuer hostednetwork)
        password: WLAN-Passwort (optional, fuer hostednetwork)

    Returns:
        True wenn erfolgreich oder bereits aktiv
    """
    global _active_method

    ssid = ssid or _DEFAULT_SSID
    password = password or _DEFAULT_PASSWORD

    # ── Methode 1: Tethering API (mit allen Profilen) ──
    logger.info("Starte Hotspot (Tethering API)...")
    success, output = _run_powershell(_START_TETHERING_PS)

    if output == "ALREADY_ON":
        logger.info("Hotspot war bereits aktiv (Tethering)")
        _active_method = "tethering"
        return True
    elif output == "Success" or (success and "Error" not in output):
        logger.info("Hotspot erfolgreich gestartet (Tethering)")
        _active_method = "tethering"
        return True

    # Tethering hat nicht funktioniert - Fallback
    logger.info(f"Tethering API fehlgeschlagen: {output}")

    # ── Methode 2: netsh hostednetwork (Offline!) ──
    logger.info("Versuche netsh hostednetwork (Offline-Methode)...")

    if not _is_hostednetwork_supported():
        logger.warning("Hosted Network wird von diesem WLAN-Treiber nicht unterstuetzt")
        logger.error("Hotspot konnte nicht gestartet werden (kein Internet, kein Hosted Network)")
        return False

    # Konfigurieren
    _run_netsh(["wlan", "set", "hostednetwork", f"mode=allow", f"ssid={ssid}", f"key={password}"])

    # Starten
    success, output = _run_netsh(["wlan", "start", "hostednetwork"])

    if success and ("gestartet" in output or "started" in output):
        logger.info(f"Hotspot gestartet (hostednetwork): SSID={ssid}")
        _active_method = "hostednetwork"
        return True

    # Evtl. schon aktiv
    if "bereits gestartet" in output or "already started" in output:
        logger.info("Hotspot war bereits aktiv (hostednetwork)")
        _active_method = "hostednetwork"
        return True

    logger.error(f"Hotspot-Start fehlgeschlagen: {output}")
    return False


def stop_hotspot() -> bool:
    """Stoppt den Hotspot (beide Methoden)

    Returns:
        True wenn erfolgreich oder bereits aus
    """
    global _active_method
    stopped = False

    # Tethering stoppen
    if _active_method != "hostednetwork":
        logger.info("Stoppe Hotspot (Tethering)...")
        success, output = _run_powershell(_STOP_TETHERING_PS)
        if output in ("ALREADY_OFF", "NOT_RUNNING", "Success") or success:
            stopped = True

    # Hostednetwork stoppen (immer versuchen, falls es laeuft)
    if _active_method == "hostednetwork" or not stopped:
        logger.info("Stoppe Hotspot (hostednetwork)...")
        success, output = _run_netsh(["wlan", "stop", "hostednetwork"])
        if success or "nicht gestartet" in output or "not started" in output:
            stopped = True

    if stopped:
        logger.info("Hotspot gestoppt")
        _active_method = ""
    else:
        logger.warning("Hotspot-Stop: Status unklar")

    return stopped


def is_hotspot_active() -> bool:
    """Prueft ob der Hotspot aktiv ist (beide Methoden)"""
    # Tethering pruefen
    success, output = _run_powershell(_CHECK_TETHERING_PS)
    if output == "On":
        return True

    # Hostednetwork pruefen
    success, output = _run_netsh(["wlan", "show", "hostednetwork"])
    if success and ("Status" in output or "Zustand" in output):
        # "Status : Started" / "Zustand : Gestartet"
        if "Started" in output or "Gestartet" in output:
            return True

    return False


def ensure_hotspot_state(should_be_active: bool) -> bool:
    """Stellt sicher dass der Hotspot im gewuenschten Zustand ist

    Args:
        should_be_active: True = Hotspot soll an sein, False = soll aus sein

    Returns:
        True wenn Zustand erreicht wurde
    """
    if should_be_active:
        return start_hotspot()
    else:
        return stop_hotspot()
