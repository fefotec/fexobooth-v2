"""Windows Hotspot Steuerung - Offline-fähig

Startet/stoppt einen WLAN-Hotspot für die Foto-Galerie.
Funktioniert auch OHNE Internetverbindung!

Methoden (in Prioritätsreihenfolge):
1. Windows Tethering API mit beliebigem Connection Profile
2. netsh wlan hostednetwork (Offline-Fallback)
"""

import subprocess
import sys
import threading
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Welche Methode beim letzten Start verwendet wurde
_active_method: str = ""  # "tethering" oder "hostednetwork"

# 2.4.65: Start/Stop laufen aus mehreren Threads (App-Start, Admin-Speichern,
# Hotspot-Waechter). Zwei PowerShell-Tethering-Aufrufe gleichzeitig wuerden
# sich gegenseitig in die Quere kommen — deshalb immer nur einer.
_hotspot_lock = threading.RLock()

# Standard SSID/Passwort (werden von start_hotspot überschrieben)
_DEFAULT_SSID = "fexobox-gallery"
_DEFAULT_PASSWORD = "fotobox123"

# ─────────────────────────────────────────────
# PowerShell: Tethering API (mit allen Profilen, nicht nur Internet!)
# ─────────────────────────────────────────────

# ⚠️ ACHTUNG BEI AENDERUNGEN: Diese Scripts sind NORMALE Python-Strings und
# werden NICHT mit .format() verarbeitet. Geschweifte Klammern gehoeren hier
# deshalb EINFACH geschrieben — NIE doppelt!
#
# Warum der Hinweis (Bug gefunden 18.08.2026):
# Bis 2.4.26 standen hier doppelte Klammern `{{ }}` (Rest einer alten
# .format()-Nutzung). PowerShell versteht `if (...) {{ ... }}` aber als
# "Block, der einen Script-Block ENTHAELT" — der innere Teil wird nie
# ausgefuehrt, sondern nur als Text ausgegeben. Ergebnis: Der Hotspot wurde
# NIE gestartet, NIE gestoppt, und Python hat die Text-Ausgabe trotzdem als
# Erfolg gewertet ("Hotspot erfolgreich gestartet"). Ein stiller Blindgaenger.
#
# `__EXCLUDE_SSID__` wird per .replace() ersetzt (bewusst kein .format(),
# damit die Klammer-Falle nicht zurueckkommt).

_START_TETHERING_PS = '''
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

# SSID, die NICHT als Anker benutzt werden soll (= das gerade verbundene
# Firmen-WLAN). Wird der Hotspot ueber das Firmen-Profil aufgezogen, teilt
# Windows die Firmen-Verbindung ueber dieselbe WLAN-Karte (ICS) — und genau
# dabei verliert die Box ihre IP-Adresse vom Firmen-Router.
$excludeSsid = '__EXCLUDE_SSID__'

$tetheringManager = $null
$usedProfile = ''
$fallbackManager = $null
$fallbackProfile = ''

# Methode 1: Alle Connection Profiles durchprobieren (funktioniert auch ohne Internet!)
# Reihenfolge: alles ausser dem Firmen-WLAN zuerst, Firmen-WLAN nur als Notnagel.
$profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
foreach ($profile in $profiles) {
    try {
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
        if ($tm) {
            $profileName = ''
            try { $profileName = [string]$profile.ProfileName } catch { $profileName = '' }
            if ($excludeSsid -ne '' -and $profileName -eq $excludeSsid) {
                if (-not $fallbackManager) {
                    $fallbackManager = $tm
                    $fallbackProfile = $profileName
                }
                continue
            }
            $tetheringManager = $tm
            $usedProfile = $profileName
            break
        }
    } catch { continue }
}

# Notnagel: doch das Firmen-Profil, wenn es sonst gar keinen Anker gibt
if (-not $tetheringManager -and $fallbackManager) {
    $tetheringManager = $fallbackManager
    $usedProfile = $fallbackProfile
    Write-Output "USED_EXCLUDED_PROFILE"
}

# Methode 2: Internet-Profil als letzter Versuch
if (-not $tetheringManager) {
    try {
        $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
        if ($connectionProfile) {
            $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
            try { $usedProfile = [string]$connectionProfile.ProfileName } catch { $usedProfile = '' }
        }
    } catch {}
}

if (-not $tetheringManager) {
    Write-Output "NO_PROFILE"
    exit 1
}

Write-Output "PROFILE=$usedProfile"

# Status pruefen
$state = $tetheringManager.TetheringOperationalState
if ($state -eq "On") {
    Write-Output "ALREADY_ON"
    exit 0
}

# Starten
try {
    $result = Await ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    Write-Output ("STATUS=" + [string]$result.Status)
    if ([string]$result.Status -eq "Success") { exit 0 }
    exit 1
} catch {
    Write-Output "ERROR: $_"
    exit 1
}
'''

_STOP_TETHERING_PS = '''
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

$tetheringManager = $null

# Alle Connection Profiles durchprobieren
$profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
foreach ($profile in $profiles) {
    try {
        $tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
        if ($tm -and $tm.TetheringOperationalState -eq "On") {
            $tetheringManager = $tm
            break
        }
    } catch { continue }
}

if (-not $tetheringManager) {
    # Fallback: Internet-Profil
    try {
        $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
        if ($connectionProfile) {
            $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
        }
    } catch {}
}

if (-not $tetheringManager) {
    Write-Output "NOT_RUNNING"
    exit 0
}

$state = $tetheringManager.TetheringOperationalState
if ($state -eq "Off") {
    Write-Output "ALREADY_OFF"
    exit 0
}

try {
    $result = Await ($tetheringManager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    Write-Output ("STATUS=" + [string]$result.Status)
    if ([string]$result.Status -eq "Success") { exit 0 }
    exit 1
} catch {
    Write-Output "ERROR: $_"
    exit 1
}
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
# Dummy-WLAN-Profil sicherstellen
# ─────────────────────────────────────────────
# Ohne mind. ein gespeichertes WLAN-Profil schlaegt
# NetworkOperatorTetheringManager.CreateFromConnectionProfile()
# fehl - auch wenn die Box nie Internet haben wird. Ein
# offenes, nicht-auto-verbindendes Dummy-Profil reicht damit
# die Windows-API einen Ankerpunkt hat.

_DUMMY_PROFILE_NAME = "FexoBoothDummy"
_DUMMY_PROFILE_XML = '''<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>FexoBoothDummy</name>
    <SSIDConfig>
        <SSID>
            <name>FexoBoothDummy</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
        </security>
    </MSM>
</WLANProfile>
'''


def _ensure_wlan_profile_exists() -> bool:
    """Stellt sicher, dass das Dummy-WLAN-Profil als Anker existiert.

    Zwei Gruende:

    1. Auf frisch geklonten Tablets gibt es gar keine gespeicherten
       WLAN-Profile -> CreateFromConnectionProfile() findet keinen Ankerpunkt
       und gibt immer null zurueck.
    2. Seit 2.4.27 zusaetzlich wichtig: Der Hotspot soll NICHT ueber das
       Firmen-WLAN-Profil aufgezogen werden (sonst teilt Windows die
       Firmen-Verbindung ueber dieselbe WLAN-Karte und die Box verliert ihre
       IP-Adresse vom Firmen-Router). Dafuer muss es immer ein neutrales
       Profil geben — auch dann, wenn schon andere Profile da sind.

    Das Dummy-Profil ist offen, heisst 'FexoBoothDummy' und steht auf
    "manuell verbinden" — es verbindet sich also nie mit irgendetwas.

    Returns:
        True wenn das Dummy-Profil vorhanden ist (schon oder neu angelegt)
    """
    if sys.platform != "win32":
        return False

    # Pruefen ob GENAU das Dummy-Profil schon existiert
    success, output = _run_netsh(["wlan", "show", "profiles"])
    if not success:
        logger.warning("netsh wlan show profiles fehlgeschlagen")
        return False

    if _DUMMY_PROFILE_NAME in output:
        logger.debug(f"Hotspot-Anker: Profil '{_DUMMY_PROFILE_NAME}' bereits vorhanden")
        return True

    logger.info(f"Hotspot-Anker: Lege neutrales Profil '{_DUMMY_PROFILE_NAME}' an")

    # XML in Temp-Datei schreiben
    import tempfile
    import os
    try:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8")
        tmp.write(_DUMMY_PROFILE_XML)
        tmp.close()
        xml_path = tmp.name
    except Exception as e:
        logger.error(f"Konnte Dummy-Profil-XML nicht erstellen: {e}")
        return False

    try:
        # Dummy-Profil hinzufuegen (user=current verhindert Group-Policy-Eingriff)
        success, output = _run_netsh(["wlan", "add", "profile", f"filename={xml_path}", "user=current"])
        if success:
            logger.info(f"Dummy-WLAN-Profil '{_DUMMY_PROFILE_NAME}' angelegt")
            return True
        else:
            logger.error(f"netsh wlan add profile fehlgeschlagen: {output}")
            return False
    finally:
        try:
            os.unlink(xml_path)
        except Exception:
            pass


# ─────────────────────────────────────────────
# Oeffentliche API
# ─────────────────────────────────────────────

def _parse_tethering_output(output: str) -> dict:
    """Zerlegt die Ausgabe der Tethering-Scripts in verwertbare Werte.

    Seit 2.4.27 melden die Scripts klar definierte Zeilen (PROFILE=, STATUS=,
    ALREADY_ON, NO_PROFILE, ...). Alles andere gilt bewusst als FEHLER — vorher
    wurde jede unbekannte Ausgabe als Erfolg durchgewinkt, was den kaputten
    Hotspot-Start jahrelang verdeckt hat.
    """
    result = {"status": "", "profile": "", "used_excluded": False, "raw": output}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("PROFILE="):
            result["profile"] = line[len("PROFILE="):].strip()
        elif line.startswith("STATUS="):
            result["status"] = line[len("STATUS="):].strip()
        elif line == "USED_EXCLUDED_PROFILE":
            result["used_excluded"] = True
        elif line in ("ALREADY_ON", "ALREADY_OFF", "NOT_RUNNING", "NO_PROFILE"):
            result["status"] = line
        elif line.upper().startswith("ERROR"):
            result["status"] = line
    return result


def _get_ssid_to_avoid() -> str:
    """Firmen-WLAN, das NICHT als Hotspot-Anker dienen darf (leer = egal).

    Nur relevant, wenn die Box gerade IM Firmen-WLAN haengt (Werkstatt).
    Beim Kunden ist das nie der Fall -> leerer String -> Verhalten wie bisher.
    """
    try:
        from src.utils.company_wlan import (
            COMPANY_WLAN_SSID,
            OTHER_COMPANY_SSIDS,
            get_connected_ssid,
        )
        connected = get_connected_ssid()
        if connected and connected in ([COMPANY_WLAN_SSID] + OTHER_COMPANY_SSIDS):
            return connected
    except Exception as e:
        logger.debug(f"Hotspot: Firmen-WLAN-Pruefung uebersprungen ({e})")
    return ""


def start_hotspot(ssid: str = "", password: str = "") -> bool:
    """Startet den WLAN-Hotspot (funktioniert auch ohne Internet!)

    Versucht in Reihenfolge:
    1. Windows Tethering API (bevorzugt ein NEUTRALES Connection Profile)
    2. netsh wlan hostednetwork (Offline-Fallback)

    Args:
        ssid: WLAN-Name (optional, fuer hostednetwork)
        password: WLAN-Passwort (optional, fuer hostednetwork)

    Returns:
        True wenn erfolgreich oder bereits aktiv
    """
    with _hotspot_lock:
        return _start_hotspot_locked(ssid, password)


def _start_hotspot_locked(ssid: str, password: str) -> bool:
    global _active_method

    ssid = ssid or _DEFAULT_SSID
    password = password or _DEFAULT_PASSWORD

    # ── Pre-Step: Dummy-WLAN-Profil sicherstellen ──
    # Ohne mind. ein gespeichertes Profil findet die Tethering API nichts.
    # Passiert auf frisch geklonten Tablets (sonst nur "NO_PROFILE").
    # Ausserdem ist es der neutrale Anker, damit der Hotspot nicht ueber das
    # Firmen-WLAN aufgezogen wird (2.4.27).
    _ensure_wlan_profile_exists()

    # ── Methode 1: Tethering API ──
    avoid_ssid = _get_ssid_to_avoid()

    # 2.4.27: Wurde in diesem App-Lauf bereits bewiesen, dass der Hotspot auf
    # DIESER Box das Firmen-WLAN abwuergt, bleibt er im Firmen-WLAN aus.
    # In der Werkstatt sind Dashboard-Meldung und Updates wichtiger als der
    # Gast-Hotspot; beim Kunden greift das nie (dort ist avoid_ssid leer).
    if avoid_ssid:
        try:
            from src.utils.company_wlan import hotspot_conflicts_with_company_wlan
            if hotspot_conflicts_with_company_wlan():
                logger.info(
                    f"Hotspot: Start uebersprungen — er blockiert auf dieser Box das "
                    f"Firmen-WLAN '{avoid_ssid}' (gilt nur in der Werkstatt)"
                )
                return False
        except Exception as e:
            logger.debug(f"Hotspot: Konflikt-Merker nicht lesbar ({e})")

    if avoid_ssid:
        logger.info(
            f"Starte Hotspot (Tethering API) — Firmen-WLAN '{avoid_ssid}' wird als "
            f"Anker gemieden (sonst verliert die Box ihre IP-Adresse)"
        )
    else:
        logger.info("Starte Hotspot (Tethering API)...")

    script = _START_TETHERING_PS.replace("__EXCLUDE_SSID__", avoid_ssid)
    success, output = _run_powershell(script)
    parsed = _parse_tethering_output(output)

    if parsed["profile"]:
        logger.info(f"Hotspot: Tethering-Anker = Profil '{parsed['profile']}'")

    if parsed["status"] == "ALREADY_ON":
        # Lief schon: Es wurde NICHTS umgestellt — auch wenn als Anker nur das
        # Firmen-WLAN in Frage kam. Deshalb hier bewusst keine Warnung
        # (Feld-Log 18.08. 11:30: sah nach Problem aus, war aber ein No-Op).
        if parsed["used_excluded"]:
            logger.debug(
                f"Hotspot: Anker waere nur '{avoid_ssid}' gewesen — egal, "
                f"der Hotspot lief bereits (nichts umgestellt)"
            )
        logger.info("Hotspot war bereits aktiv (Tethering)")
        _active_method = "tethering"
        return True

    if parsed["used_excluded"]:
        # Jetzt zaehlt es wirklich: Der Hotspot wird NEU ueber die
        # Firmen-Verbindung aufgezogen — genau die Konstellation, die einer
        # Box die IP-Adresse kosten kann.
        logger.warning(
            f"Hotspot: Kein neutrales Profil gefunden — musste doch das Firmen-WLAN "
            f"'{avoid_ssid}' als Anker nehmen (Firmen-Verbindung kann darunter leiden)"
        )

    if parsed["status"] == "Success":
        logger.info("Hotspot erfolgreich gestartet (Tethering)")
        _active_method = "tethering"
        return True

    # Tethering hat nicht funktioniert - Fallback
    logger.info(
        f"Tethering API fehlgeschlagen (Status='{parsed['status'] or 'unbekannt'}', "
        f"Exit-ok={success}): {parsed['raw'].strip()[:200]}"
    )

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
    with _hotspot_lock:
        return _stop_hotspot_locked()


def _stop_hotspot_locked() -> bool:
    global _active_method
    stopped = False

    # Tethering stoppen
    if _active_method != "hostednetwork":
        logger.info("Stoppe Hotspot (Tethering)...")
        success, output = _run_powershell(_STOP_TETHERING_PS)
        parsed = _parse_tethering_output(output)
        logger.debug(f"Hotspot-Stop: Status='{parsed['status'] or 'unbekannt'}'")
        if parsed["status"] in ("ALREADY_OFF", "NOT_RUNNING", "Success"):
            stopped = True
        else:
            logger.warning(
                f"Hotspot-Stop (Tethering) unklar: {parsed['raw'].strip()[:200]}"
            )

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
